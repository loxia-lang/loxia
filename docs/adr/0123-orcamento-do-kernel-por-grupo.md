# ADR-0123 — Orçamento do kernel por grupo, tabela única e SHA-256 vendorizado

- **Status:** proposed
- **Data:** 2026-11-20
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0071](0071-primitivas-de-runtime.md) (kernel),
  [ADR-0072](0072-stdlib-batteries.md) (stdlib e camadas),
  [ADR-0079](0079-stdlib-t2.md) (15 → 17), [ADR-0094](0094-kernel-io-flush-e-read-utf8.md)
  (17 → 19), [ADR-0095](0095-processos-streams-poll.md) (19 → 29),
  [ADR-0119](0119-fs-open-handles-e-erro-de-host.md) (29 → 33),
  [ADR-0122](0122-contrato-de-data-e-instante.md),
  [ADR-0124](0124-fmt-self-host-e-pacotes-por-repo.md),
  Discussions [#31](https://github.com/loxia-lang/loxia/discussions/31) (net),
  [#33](https://github.com/loxia-lang/loxia/discussions/33) (bindgen/tabela),
  [#58](https://github.com/loxia-lang/loxia/discussions/58) (fs adiado)
- **Implementação:** `loxia_core/execution/primitives.py` (`group`, `GROUP_BUDGET`),
  `runtime/gen_kernel.py` / `runtime/kernel_gen.h`, `runtime/digest.c`,
  `loxia_core/backend/driver.py` (`RUNTIME_NAMES`), `loxia/cli_commands.py`
  (`capabilities`), `tests/test_primitives.py`, `tests/test_bundle.py`,
  `std/hash.lx`, `std/fs.lx`, `docs/spec/`

## Contexto

O kernel está em **33 primitivas** e o orçamento nominal era ~30. A trajetória está
registrada: 15 → 17 ([ADR-0079](0079-stdlib-t2.md)) → 19
([ADR-0094](0094-kernel-io-flush-e-read-utf8.md)) → 29
([ADR-0095](0095-processos-streams-poll.md)) → 33
([ADR-0119](0119-fs-open-handles-e-erro-de-host.md), que somou `fs.open/read/write/close`
sem re-basear o teto). Ou seja: o número que devia forçar uma decisão já foi ultrapassado
sem decisão.

Ao mesmo tempo, a próxima leva de capacidade já tem consumidor nomeado:

- o **`loxia fmt` em Lox** ([ADR-0124](0124-fmt-self-host-e-pacotes-por-repo.md)) precisa de
  reescrita atômica (`rename`), limpeza (`remove`), diretório (`mkdir`) e mtime/tamanho
  (`stat`) para não corromper arquivo e para pular o que não mudou;
- o **lock self-hosted** precisa de SHA-256, porque o `loxia.lock` guarda `sha256` da árvore
  `.lx` ([ADR-0105 §2](0105-dependencias-git.md)).

E a "tabela de primitivas" já existe: `PRIMITIVES` em
[`primitives.py`](../../loxia_core/execution/primitives.py) é a fonte única (nome Lox,
símbolo C, assinatura, oráculo Python, `ambient`, `site`, `needs_interpreter`) e
`runtime/gen_kernel.py` gera `kernel_gen.h` (`make primitives`). O que falta não é formato:
é **orçamento executável** e um lugar explícito para o custo de cada primitiva.

A discussão [#33](https://github.com/loxia-lang/loxia/discussions/33) deixou a migração da
tabela para TOML parked com o gatilho "kernel > ~30 ou um segundo gerador". O gatilho de
número disparou; o de segundo gerador não.

## Decisão

### 1. Grupo e orçamento executável na tabela única

`Primitive` ganha `group: str`; `PRIMITIVES` continua a fonte; `GROUP_BUDGET` mora no mesmo
módulo e um teste (`test_kernel_budget`) falha quando um grupo ou o total estoura. O teto
deixa de ser discussão oral: ou a primitiva cabe no grupo, ou o ADR muda a tabela.

`loxia capabilities --json` publica `primitives` (nome, grupo, `ambient`, `site`) para que
tooling e documentação leiam a tabela em vez de repeti-la.

| Grupo | Hoje | Teto | O que entra |
| --- | --- | --- | --- |
| `core` | 5 | 5 | `substr`, `join`, `charCodeAt`, `fromCodePoint`, `args` |
| `io` | 8 | 8 | stdio, arquivo inteiro, UTF-8, `flush` |
| `fs` | 6 | **11** | `+ rename`, `+ remove`, `+ mkdir`, `+ stat` (+ `readBytes` quando `Bytes`) |
| `os` | 2 | 2 | `exit`, `getenv` |
| `proc` | 10 | 10 | spawn, streams, `poll` |
| `time` | 2 | 2 | `monotonic` só com consumidor e ADR (sem reserva) |
| `digest` | 0 | 2 | `+ sha256` (+ `sha256Bytes` quando `Bytes`) |
| **total** | **33** | **40** | |

> **Emenda por [ADR-0125](0125-bytes-tipo-binario.md):** `fs.readBytes` (+1 em `fs`) e
> `digest.sha256Bytes` (+1 em `digest`) entram com o tipo `Bytes`; para o total caber em 40,
> `time.monotonic` deixa de ser reserva e só entra com consumidor. Os dois ainda não têm
> implementação.

Módulos nativos **não** entram nesses 40: cada um tem a própria tabela e orçamento
(`NATIVE_MODULE_BUDGET`), porque não são SO/representação e não poluem o kernel. O primeiro
é `sqlite3` com 20 ([ADR-0126](0126-modulo-nativo-embutido-sqlite.md)); o teste de orçamento
cobre as duas tabelas.

### 2. O que é aprovado agora

**`fs` — capacidade de mutação (4 primitivas).** Driver: o formatador self-hosted.

- `fs.rename(src, dst) -> Nil` — rename atômico no mesmo sistema de arquivos; é o que
  permite `tmp` + `rename` sem janela de arquivo truncado.
- `fs.remove(path) -> Nil` — remove **arquivo**; diretório não vazio é erro (remoção de
  árvore não tem consumidor e é uma armadilha).
- `fs.mkdir(path) -> Nil` — um nível; `mkdirAll` é wrapper em `std.fs` (loop), não primitiva.
- `fs.stat(path) -> (Int, Int, Bool)` — `(size, mtimeMs, isDir)`, sem seguir a discussão de
  symlink (não há consumidor); `mtimeMs` é o que o fmt usa para pular arquivo inalterado.

**`digest` — SHA-256 (1 primitiva, pura).**

- `digest.sha256(text: String) -> String` — hex minúsculo de 64 caracteres sobre os **bytes
  UTF-8** do texto (a mesma convenção de `std.hash` e `std.convert`).
- É **pura**: não toca SO, não é `ambient`, entra no corpus I1/I3 e no diferencial do
  backend como qualquer função determinística.
- `std.hash.sha256(text)` reexporta a primitiva; o namespace nativo `digest` fica para o
  baixo nível (e para um eventual `hmac`, que exigiria ADR próprio).
- Implementação **vendorizada** em `runtime/digest.c` (8ª unidade, FIPS 180-4, ~200 linhas),
  sem dependência externa; `RUNTIME_NAMES` ganha a unidade e
  `test_runtime_lista_todas_as_unidades` continua valendo. Vetores NIST no teste (vazio,
  `"abc"`, 1 MiB, UTF-8 multi-byte, `\0` no meio).

**Negado por ora:** `io.isatty` (o `std.term` é explícito: quem chama decide a cor) e
`time.monotonic` (nenhum consumidor mede duração; `std.test` não cronometra e o bench é
Python). `net` continua parked ([#31](https://github.com/loxia-lang/loxia/discussions/31)),
e `seek`/`tell`/`r+` continuam fora ([#58](https://github.com/loxia-lang/loxia/discussions/58)):
`stat`/`rename` não são `seek`.

### 3. A tabela fica em Python; o #33 fecha

Não migrar para TOML. `PRIMITIVES` já é dado declarativo, mypy-checado, e cada linha carrega
o callable Python que é o **oráculo**; separar tabela de implementação cria duas fontes de
verdade — exatamente o que a dupla `primitives.py` + `gen_kernel.h` evita. Formato neutro só
paga com um segundo gerador (bindgen/FFI, parked). O #33 fecha com esse critério e reabre
com segundo gerador.

### 4. Custo explícito de uma primitiva

Toda primitiva nova paga os dez itens abaixo; o ADR do grupo deve dizer quais deles mudam:

1. **Duas implementações** — oráculo Python e C, com o mesmo comportamento byte a byte.
2. **ABI gerada** — assinatura (`STRING`, `INT`, `ListTy`, união, handle como `INT`) e
   `site` para o panic apontar a chamada.
3. **Erro e causa** — `RuntimeError` com `kind` estável no kernel; `Result` na stdlib.
4. **Sandbox** — `SANDBOX_DENIED_NAMES`/prefixos e teste; primitiva pura não entra na lista.
5. **Determinismo** — `ambient` sai do corpus I1/I3; pura tem que ser determinística em toda
   plataforma (é o motivo de `sin`/`log` estarem fora).
6. **Memória e pilha** — alocação só por `lox_alloc`/`lox_alloc_atomic`, sem `free`, sem
   ponteiro para o heap do GC atravessando alocação, orçamento de pilha respeitado.
7. **Build e link** — unidade nova entra em `RUNTIME_NAMES`, muda a chave do cache de build e,
   se houver biblioteca externa, muda a linha de link e a matriz de CI. Hoje o link nativo é
   `cc` + `-lgc`; cada biblioteca a mais é uma exigência permanente para todo usuário que
   compila.
8. **Documentação** — `builtins_docs.py`, `docs/spec/`, página de stdlib e caso golden.
9. **Orçamento** — o grupo e o total (tabela acima).
10. **Segurança** — primitiva de cripto é promessa de segurança, não só de ABI.

### 5. Fronteira de criptografia

SHA-256 aqui é **integridade de conteúdo público** (hash de árvore, cache, checksum). Não é
criptografia de segredo: nada de AES, RSA, HMAC, PBKDF2, TLS ou geração de chave na stdlib.
Um consumidor que trate segredo, entropia ou comparação em tempo constante pede ADR próprio,
com modelo de ameaça — e provavelmente um pacote, não o kernel.

## Consequências

### Positivas

- O teto vira teste; ninguém "só adiciona mais uma" sem mudar a tabela.
- `fs.rename`/`stat` destravam o formatador self-hosted (ADR-0124) e `sha256` destrava o lock.
- Zero dependência externa: o build continua `cc` + `libgc`.
- A tabela publicada em `capabilities` acaba com a doc paralela de primitivas.
- `sha256` é o caso mais fácil de justificar no kernel: puro, determinístico, com vetores
  públicos e consumidor nomeado.

### Negativas / custos

- O teto dobra (15 → 40) em cinco ADRs; cada grupo novo é mais uma decisão.
- Passamos a manter código criptográfico próprio. SHA-256 é estável e simples, mas é nosso:
  exige vetores, revisão e cuidado com tamanho/overflow.
- 8ª unidade no runtime: mais um arquivo no build, no cache e no teste de bundle.
- `fs.stat` devolve tupla de três campos; precisão de `mtime` depende do sistema de arquivos
  e precisa ser documentada (segundos em alguns, ns em outros).
- `fs.remove` só arquivo e `mkdir` não recursivo transferem complexidade para wrappers.
- Kernel continua POSIX-only; Windows segue fora (e `stat`/`rename` seriam o começo de outra
  conversa).

### Neutras

- `proc` e `io` ficam congelados nos tetos atuais: crescer ali exige ADR, não sobra de grupo.
- O campo `group` não muda a ABI gerada; é metadado de orçamento e documentação.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Puxar OpenSSL/libcrypto e fazer shim | Dependência externa em todo build, drift de versão (1.1.1/3.x/LibreSSL), link estático e WASM, licença a revisar; e "ganhar um monte de coisa" não acontece: cada operação continuaria sendo uma primitiva com ABI tipada própria (contextos de AES/RSA não cabem em `String -> String`). Cripto de segredo é promessa de segurança, não biblioteca de conveniência. |
| SHA-256 em Lox puro | `List[Int]` custa ~28 bytes por byte de entrada (1 MB ≈ 28 MB) e é lento para hashear árvore; sem `Bytes` não há representação compacta. |
| `Bytes` primeiro, SHA-256 depois em Lox | É a sequência correta no longo prazo, mas o lock não pode esperar um tipo novo; e o tipo não fica mais fácil por causa do hash. |
| Migrar a tabela para TOML ([#33](https://github.com/loxia-lang/loxia/discussions/33)) | Sem segundo gerador; separa a tabela do oráculo; o problema real era orçamento, não formato. |
| Sem teto por grupo, só total | O total não diz onde crescer; crescimento por simetria volta. |
| `fs.remove` recursivo e `mkdir -p` na primitiva | Mais superfície de SO e de erro; o wrapper em Lox resolve e é testável. |

## Como verificar

- `test_kernel_budget`: soma por grupo e total contra `GROUP_BUDGET`.
- `test_runtime_lista_todas_as_unidades` e `make primitives` sem diff.
- Vetores NIST em `tests/test_primitives.py` e caso diferencial `std_hash_sha256.lx` no
  backend (interpretado × nativo).
- `loxia capabilities --json` com `primitives`, e o teste de contrato do CLI.
- Sandbox: `digest.sha256` permitido; `fs.rename`/`remove`/`mkdir`/`stat` negados, com teste.

Critério para revisitar: total acima de 40, necessidade de Windows, um segundo gerador que
precise da tabela em formato neutro, ou um consumidor real de segredo/entropia (que vem com
ADR próprio).

## Referências

- [`runtime/README.md`](../../runtime/README.md) — ABI, GC, pilha e unidades.
- [ADR-0071](0071-primitivas-de-runtime.md) — por que kernel é SO/representação.
- [ADR-0095](0095-processos-streams-poll.md) — o teto de ~30 e o custo de handles.
- [ADR-0119](0119-fs-open-handles-e-erro-de-host.md) — erro de host e handles de arquivo.
- FIPS 180-4 (Secure Hash Standard) e vetores NIST CAVP.
