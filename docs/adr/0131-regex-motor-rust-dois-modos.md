# ADR-0131 — Regex: motor Rust com dois modos (linear padrão, backtracking opt-in)

- **Status:** accepted (implementado no PR #119) — supersede o [ADR-0130](0130-regex-pcre2-embutido.md)
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

`Mode.Full` é escolha do dev no `compile`, não default. Erro de sintaxe vira `Result`
com `RegexError.kind`; o limite de backtracking estourado em `find` vira `RuntimeError`
(`regex match limit exceeded.`), estável e determinístico nos dois motores.

### 2. ABI C e segurança de FFI

- O crate exporta `extern "C"` (`cdylib` para o `run`, `staticlib` para `--emit=exe`):
  `loxr_compile`, `loxr_match`, `loxr_group_names`, `loxr_free`, `loxr_abi_version`.
- **Todo** símbolo `extern "C"` é envolvido em `std::panic::catch_unwind`; panic nunca
  cruza a FFI (desde o Rust 1.81 o unwind através de `extern "C"` aborta o processo). Erro
  interno vira código de retorno + mensagem estática.
- O **hook de panic é silenciado** no init do crate: `catch_unwind` sozinho não impede o
  hook padrão de escrever `thread ... panicked` no stderr — e stderr é canal do I1. O hook
  é instalado uma vez (`Once`); como `set_hook` é global do processo, ele vale para todo
  Rust carregado no host — hoje só este crate, mas é um efeito de processo, não local.
- Perfil de release com `panic = "unwind"` (nunca `abort`): o `catch_unwind` é o que
  transforma bug interno em erro do Loxia.
- Tabela de handles 1-based, `free` idempotente, sem finalizer (Boehm não é
  determinístico); `abi_version` é conferida na carga. O teto é de 4096 handles vivos. A
  memória do Rust fica **fora** do heap Boehm do binário: o contrato é por programa
  (`size_limit` de 10 MiB no linear e nos sub-regex delegados do full, `max_prog_size` de
  100.000 instruções e cache DFA de 2 MiB no full), não um orçamento total de bytes
  (decisão do #122, §2.1).
- Offsets: o `regex` devolve bytes UTF-8; a conversão para code points acontece no Rust,
  num lugar só. O `out_offset` do erro de compilação é o **byte** do primeiro erro de
  sintaxe (ou `-1` quando desconhecido); quando os dois modos rejeitam o padrão, reportam o
  mesmo valor (#121).

### 2.1 Atualização (2026-11-22, #121 e #122)

- **#121 — span do erro de sintaxe.** `loxr_compile` passa a escrever `out_offset`:
  `regex-syntax` fornece o começo do span no modo linear. No full, o span interno do
  `fancy-regex`/`regex-automata` é **relativo ao fragmento delegado** (o build compila a
  substring do `Delegate`), então nunca é usado como offset público: quando o parser linear
  também rejeita o padrão, vale o primeiro erro dele (os dois modos reportam o mesmo byte);
  quando o parser linear aceita (sintaxe exclusiva do full), vale a posição do
  `fancy-regex`. O offset é em **bytes**, como o resto do ABI; a API expõe em
  `RegexError.offset`.
- **#121 — classificação estável.** Erro de análise do full que não é sintaxe nem tamanho
  (recursão à esquerda, recursão infinita, lookbehind não constante, recurso não suportado)
  vira `LOXR_ERR_ENGINE` / `RegexError.kind == "engine"` com offset `-1`; erro de sintaxe de
  backref/grupo nomeado continua `syntax` com o offset canônico. Padrão grande demais deixa
  de ser reportado como `syntax`: vira `LOXR_ERR_TOO_BIG` / kind `size`, com offset `-1`.
- **#122 — memória.** `Mode.Full` passa a explicitar `delegate_size_limit(10 MiB)` e
  `delegate_dfa_size_limit(2 MiB)` (que já eram os defaults do `regex-automata` por baixo),
  `delegate_dfa_skip_cache_capacity_check(false)` e `max_prog_size(100.000)`. O que muda de
  fato é o teto de instruções (a expansão de subrotinas recursivas é materializada em tempo
  de compilação) e o cache estrito de lookbehind variável, que pode falhar com `size` em
  vez de ser arredondado para cima; lookbehind comum e repetição contada continuam
  compilando (teste de regressão). A decisão registrada é que a memória do Rust **não**
  entra no contrato de heap de 512 MiB (ADR-0074/0087): o limite é por programa compilado,
  multiplicado pelos 4096 handles vivos, e `close()` é a forma de liberar. Um orçamento
  total de bytes exigiria introspecção que o `fancy-regex` não oferece; o custo/benefício
  não paga trocar o motor linear por uma camada própria só para medir.
- **ABI.** `LOXR_ABI_VERSION` continua 2: assinatura, layout e códigos existentes não
  mudaram; os dois chamadores inicializam `out_offset` com `-1`, então uma lib antiga apenas
  degrada para o comportamento anterior (offset sempre `-1`, sem `-9`) sem crash. O cache
  de build é content-addressed pelo hash de `src/` + `include/`, então o fluxo normal nunca
  pareia lib antiga com binding novo; subir a versão fica reservado a uma mudança de
  assinatura/layout.

### 3. Camada e superfície

- Namespace primitivo **`regex_engine`** (neutro, evita colidir com o módulo público
  `regex`, mesmo padrão de `sqlite3`/`sqlite`): `compile(pattern, flags, mode)`,
  `find(handle, subject, start)`, `groupNames(handle)`, `free(handle)`. Quatro primitivas,
  teto 4, fora dos 40 do
  kernel. O nome é `find`, não `match`: `match` é palavra-chave da linguagem e não pode ser
  membro acessado; a função C correspondente continua `loxr_match`.
- `bundled/regex.lx`: `Regex`, `Match`, `RegexError`; `compile`/`compileFull` e
  `tryCompile`/`tryCompileFull`, `isMatch`, `find`/`findFrom`, `findAll`, `replace`,
  `replaceAll`, `split`; `$1`/`$name`/`${name}` expandido em Lox; sem callback C→Lox na v1.
  Notas de implementação (2026-11): `Mode` virou `compile`/`compileFull` porque variante de
  enum não pode ser valor default; `find` + `findFrom` porque parâmetro default em método é
  `E4001`; `$name` é a forma prática de substituição, `${name}` exige `\$` no fonte por
  causa da interpolação; `regex_engine.groupNames` é a quarta primitiva do orçamento.
- Compile devolve `Result[Regex, RegexError]`; o primitivo usa um protocolo `List[Int]`
  (`[1, handle]` / `[0, code, offset]`) porque a tabela de primitivas não tem tipo
  algébrico. `RegexError.kind` é uma categoria estável (`syntax`, `arguments`, `mode`,
  `size`, `engine`) e `RegexError.offset` é o byte do primeiro erro de sintaxe (`-1` quando
  não se aplica).
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
- `tests/cases/std_regex/*.lx` em `run` e `--emit=exe`, com `--check` limpo (nível `t4`).
  A diretiva `# requires: rust` pula o caso sem `cargo`, então o corpus não torna Rust
  pré-requisito do `make check-fast` (#120).
- Teste de panic: cada `extern "C"` tem um gatilho só de teste que dispara panic interno
  → `ERR_PANIC` estável, processo vivo (`panic_does_not_escape_any_entry_point`).
- Teste de limite: `(a+)\1$` em `Full` (backref, §7.1) → `RuntimeError` (limite de
  backtracking); em `Linear` termina. `(a+)+$` não serve: o `fancy-regex` delega ao linear.
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
