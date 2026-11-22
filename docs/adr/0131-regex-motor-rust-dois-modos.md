# ADR-0131 — Regex: motor Rust com dois modos (linear padrão, backtracking opt-in)

- **Status:** accepted (decisão; implementação pendente) — supersede o [ADR-0130](0130-regex-pcre2-embutido.md)
- **Data:** 2026-11-22
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH); revisão técnica do Gemini
  incorporada (§2, §4 e §5)
- **Relacionados:** [ADR-0130](0130-regex-pcre2-embutido.md) (superseded),
  [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) (camada nativa),
  [ADR-0127](0127-pacotes-com-codigo-nativo.md) (pacotes/artefatos nativos),
  [ADR-0128](0128-contrato-de-motores.md) (camadas),
  [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) (orçamento),
  [ADR-0071](0071-primitivas-de-runtime.md) (sem FFI genérica),
  [#114](https://github.com/loxia-lang/loxia/issues/114) e
  [#116](https://github.com/loxia-lang/loxia/issues/116)
- **Implementação:** `native/regex/` (crate Rust, `cdylib` + `staticlib`),
  `runtime/regex.c` (adaptadores Lox), `loxia_core/execution/regex_runtime.py` (ctypes),
  `loxia_core/execution/primitives.py` (namespace `regex_engine`),
  `loxia_core/backend/driver.py` (`runtime_units(imports)` e libs nativas do Rust),
  `bundled/regex.lx`, `tests/cases/std_regex/*.lx`

## Contexto

O [ADR-0130](0130-regex-pcre2-embutido.md) escolheu PCRE2 vendorizado com um motor
compartilhado entre interpretador (`ctypes`) e binário (link estático). Ao planejar a
implementação (#116), três forças reabriram a decisão:

1. **ReDoS.** PCRE2 é backtracking. "Seguro" ali significa *bounded* por limites, não
   linear; um padrão adversarial pode falhar em entrada benigna e o motor é C.
2. **Quem escreve o padrão.** O padrão pode vir do usuário conforme a superfície que o dev
   construir (flag de CLI, config, tool MCP). Se isso é possível, "padrão confiável" não é
   invariante e a linearidade vira requisito.
3. **Distribuição.** Artefato nativo é por alvo; o que o modelo atual evita é a **matriz**,
   não a plataforma, porque compila no alvo com `cc`.

O teorema que separa as opções: backreference torna o matching NP-hard e lookaround tira o
padrão das linguagens regulares; nenhum motor linear faz os dois. Logo a saída é **dois
modos**, não uma engine que faz tudo.

## Decisão

**Motor Rust — `regex` (linear, padrão) + `fancy-regex` (backtracking, opt-in) — com ABI C
própria, num crate do monorepo, distribuído em dois estágios.**

### 1. Dois modos explícitos

| Modo | Engine | Garantia | Uso |
| --- | --- | --- | --- |
| `Mode.Linear` (padrão) | `regex` | tempo linear, memória limitada por `size_limit` | padrão vindo de fora, uso geral |
| `Mode.Full` (opt-in) | `fancy-regex` | backtracking com `backtrack_limit` (padrão 1.000.000 de passos) | backref, lookaround, atômico |

`Mode.Full` é escolha do dev no `compile`, não default. A recusa/limite vira
`RegexError.limit`, estável e determinístico.

### 2. ABI C e segurança de FFI

- O crate exporta `extern "C"` (`cdylib` para o `run`, `staticlib` para `--emit=exe`):
  `loxr_compile`, `loxr_match`, `loxr_free`, `loxr_abi_version`.
- **Todo** símbolo `extern "C"` é envolvido em `std::panic::catch_unwind`; panic nunca
  cruza a FFI (desde o Rust 1.81 o unwind através de `extern "C"` aborta o processo). Erro
  interno vira código de retorno + mensagem estática.
- O **hook de panic é silenciado** no init do crate: `catch_unwind` sozinho não impede o
  hook padrão de escrever `thread ... panicked` no stderr — e stderr é canal do I1. O hook
  é instalado uma vez (`Once`) e não afeta o processo host.
- Perfil de release com `panic = "unwind"` (nunca `abort`): o `catch_unwind` é o que
  transforma bug interno em erro do Loxia.
- Tabela de handles 1-based, `free` idempotente, sem finalizer (Boehm não é
  determinístico); `abi_version` é conferida na carga.
- Offsets: o `regex` devolve bytes UTF-8; a conversão para code points acontece no Rust,
  num lugar só.

### 3. Camada e superfície

- Namespace primitivo **`regex_engine`** (neutro, evita colidir com o módulo público
  `regex`, mesmo padrão de `sqlite3`/`sqlite`): `compile(pattern, flags, mode)`,
  `match(handle, subject, start)`, `free(handle)`. Três primitivas, teto 4, fora dos 40 do
  kernel.
- `bundled/regex.lx`: `Regex`, `Match`, `RegexError`, `Mode`; `compile`,
  `isMatch`, `find`, `findAll`, `replace`, `replaceAll`, `split`; `$1`/`${name}` expandido
  em Lox; sem callback C→Lox na v1.
- Compile devolve `Result[Regex, RegexError]`; o primitivo usa um protocolo `List[Int]`
  (`[1, handle]` / `[0, offset]`) porque a tabela de primitivas não tem tipo algébrico.
- Classificação `core` (I1/I3). Sem `cargo` na máquina, `E3022` antes de executar.

### 4. Distribuição em dois estágios

**A — agora (dogfood/CI).** Crates vendorizados (`cargo vendor`) + `Cargo.lock` +
`rust-toolchain.toml`; `cargo build --release --locked --offline` no primeiro import.

- Cache **persistente**, porque o build a frio custa segundos (medido: 5,4 s com download;
  ~10 s com LTO): `$XDG_CACHE_HOME/loxia/regex/<chave>`
  (fallback `~/.cache/loxia/regex`, depois `$TMPDIR`), com `LOX_BUILD_CACHE` de override.
  Chave = hash de `Cargo.lock` + fontes do crate + `rustc -vV` + target triple + perfil/flags.
- Build atômico (diretório temporário + rename) e *lock* de arquivo: dois `loxia`
  concorrentes não compilam duas vezes.
- **Aviso de UX sem quebrar I1**: a linha `[loxia] building the regex engine (first run
  only)…` vai para stderr **somente quando stderr é TTY** e nunca em `--json`; stdout e os
  canais do diferencial ficam intocados. Sem TTY, silêncio.
- Sem `cargo`: `E3022` com instrução de instalação, antes de executar.

**B — quando a feature for para usuário final.** Wheels por plataforma de um pacote
primeiro-party `loxia-regex` (`pip install loxia[regex]`), matriz de 6 alvos
(`x86_64/aarch64 linux-gnu`, `x86_64 linux-musl`, `x86_64/aarch64 apple-darwin`,
`x86_64 windows-msvc`). O wheel principal continua puro; o estágio B não muda API nem
código Rust.

### 5. Link estático (`--emit=exe`)

A `staticlib` do Rust exige as bibliotecas nativas do próprio Rust no link final. O build
captura a lista de `rustc --print native-static-libs` (via `cargo rustc -- --print
native-static-libs`) **uma vez**, guarda no metadado do cache junto da chave do toolchain e
`_link` acrescenta essa lista — nunca hardcodar `-lpthread`/frameworks por plataforma.

### 6. Localização: monorepo

O crate vive em `native/regex/` **neste repositório**. O motor é parte do toolchain e é
versionado com a linguagem; separar em repo próprio criaria segundo trem de release, ABI
versionada e teste cruzado por artefato — o terreno do [ADR-0127](0127-pacotes-com-codigo-nativo.md),
que só se justifica quando existir consumidor externo do crate. O precedente do cliente
VS Code ([ADR-0109](0109-editor-repo-e-assets.md)) não se aplica: é outro produto, não um
componente do runtime.

### 7. Spike obrigatório antes da fase 1

Crate mínimo (`regex` + `fancy-regex`) exportando o C ABI, carregado por `ctypes`:

- medir `cargo build --release` a frio e a quente, e o tamanho de `cdylib`/`staticlib`;
- medir a latência por match via `ctypes` e o custo de conversão de offsets;
- confirmar `\p{L}`, grupos nomeados, `\p{...}` e offsets multibyte;
- `(a+)+$` sobre entrada longa: `Linear` termina; em `Full`, o limite precisa de um padrão
  com backref (`(a+)\1$`), porque o `fancy-regex` delega padrões regulares ao motor linear;
- injetar um panic de teste e provar que ele vira código de erro, não abort;
- capturar `native-static-libs` e linkar um binário de teste.

### 7.1 Resultado do spike (2026-11-22, Linux x86_64, rustc 1.93.1)

**GO**, com duas correções registradas abaixo.

| Medida | Valor |
| --- | --- |
| `cargo build --release` a frio (`CARGO_HOME` e target vazios, com download) | **5,4 s** |
| build com `lto = true` + `opt-level = "z"` | 10,1 s |
| `cdylib` | 3,2 MB → **1,7 MB** com LTO/z |
| `staticlib` | 27,9 MB → 10,6 MB |
| binário de teste linkado (staticlib) | 8,2 MB → **3,4 MB** (1,7 MB stripped) |
| binário Loxia sem regex, para comparação | 99 KB (84 KB stripped) |
| latência por match via `ctypes` | **1,4 µs** (padrão real, subject de 50 chars) |
| `native-static-libs` (Linux) | `-lgcc_s -lutil -lrt -lpthread -lm -ldl -lc` |

Correções que o spike trouxe:

1. **`(a+)+$` não exercita o `backtrack_limit`**: o `fancy-regex` delega padrões regulares
   ao motor linear. O teste de limite usa backref (`(a+)\1$`): com `backtrack_limit(10)` o
   erro volta estável em 0,03 ms. De positivo, o `Mode.Full` herda a linearidade nos
   padrões regulares.
2. **`catch_unwind` sozinho não silencia o hook de panic**: a mensagem vaza no stderr. O
   hook precisa ser instalado no init (§2), senão o I1 quebra no primeiro bug interno.

O custo que sobra é tamanho: **+1,6 MB por binário que importa regex** (1,7 MB stripped
contra 84 KB sem regex), mesmo com LTO/`opt-level="z"`. O link é condicional — quem não
importa não paga — e o estágio B pode linkar a `cdylib` em vez da `staticlib` se o tamanho
do binário virar requisito.

## Consequências

### Positivas

- **Default seguro**: padrão não confiável roda em modo linear, sem ReDoS.
- **Memória segura** na fronteira que faz parsing do padrão; sem a classe de CVE do C.
- **Completo quando pedido**: `Mode.Full` cobre backref/lookaround sem tornar o default
  inseguro.
- Unicode completo e case folding; um toolchain cobre os dois modos.
- Build mais simples que vendorizar C (`cargo` resolve o que exigiria `config.h`).
- Estágio A evita a matriz de artefatos enquanto a feature é dogfood; B não muda a API.

### Negativas / custos

- `cargo` passa a ser pré-requisito de `run` para quem usa regex (estágio A).
- Build a frio de ~5 s (10 s com LTO): mitigado por cache persistente, aviso em TTY e,
  depois, wheels.
- **+1,6 MB por binário que importa regex** (1,7 MB stripped contra 84 KB sem regex). É o
  custo real da decisão; o link condicional garante que quem não importa não paga.
- Matriz de 6 alvos e supply chain de binário no estágio B.
- `rust-toolchain.toml` + MSRV + `cargo vendor` (~5 crates) + auditoria de dependências.
- Link estático exige repassar `native-static-libs`; é fácil de esquecer e quebra só no
  `--emit=exe` (teste dedicado).
- `catch_unwind` é disciplina: um `extern "C"` novo sem guarda é um abort esperando para
  acontecer (teste de panic por símbolo).

### Neutras

- `regex_engine` é feio, mas é namespace bruto; o público continua `regex`.
- Handles são `Int` até existir tipo opaco.
- O crate pode virar repo separado no dia em que tiver consumidor externo.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| PCRE2 vendorizado (ADR-0130) | bounded, não linear; motor C; sem modo seguro para padrão não confiável |
| RE2 | C++17 + Abseil no vendor e classes Perl ASCII; pior custo e falha Unicode |
| PCRE2 + RE2 (dois motores) | dois vendors, duas semânticas, dois toolchains |
| `native-only` (só `--emit=exe`) | `run` recusaria e todo script de CI precisaria ser compilado |
| Crate em repo separado | segundo trem de release e teste cruzado por artefato sem consumidor externo |
| Motor próprio | anos para chegar a PCRE; memória insegura por construção |

## Como verificar

- Spike da §7 com números registrados neste ADR (tempo, tamanho, latência).
- `tests/cases/std_regex/*.lx` em `run` e `--emit=exe`, com `--check` limpo.
- Teste de panic: símbolo `extern "C"` recebe entrada que dispara panic interno → erro
  estável, processo vivo.
- Teste de limite: `(a+)+$` em `Full` → `RegexError.limit`; em `Linear` termina.
- Teste de link: `--emit=exe` de programa com regex passa com as libs de
  `native-static-libs`; sem elas, falha explícita (não é o caso).
- `E3022` sem `cargo`; aviso de build só em TTY; stdout idêntico ao binário.

## Referências

- [Rust `regex` — tempo linear, Unicode e `size_limit`](https://docs.rs/regex/latest/regex/)
- [`fancy-regex` — backrefs/lookaround e `backtrack_limit`](https://docs.rs/fancy-regex/latest/fancy_regex/)
- [Rust — `extern "C"` e unwinding](https://doc.rust-lang.org/reference/items/external-blocks.html)
- [`rustc --print native-static-libs`](https://doc.rust-lang.org/rustc/command-line-arguments.html)
- [ADR-0130](0130-regex-pcre2-embutido.md), [#114](https://github.com/loxia-lang/loxia/issues/114),
  [#116](https://github.com/loxia-lang/loxia/issues/116)
