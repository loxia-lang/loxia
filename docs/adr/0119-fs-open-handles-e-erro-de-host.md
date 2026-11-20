# ADR-0119 — `fs.open` com handles e o padrão `Result` para falha de host

- **Status:** accepted (implementação parcial: `fs` entregue; `proc`, `csv` e `timex` em migração)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0016](0016-api-stdlib-hibrida.md) (API da stdlib),
  [ADR-0071](0071-primitivas-de-runtime.md) (kernel), [ADR-0072](0072-stdlib-batteries.md)
  (stdlib), [ADR-0095](0095-processos-streams-poll.md) (handles de processo),
  [ADR-0118](0118-toml-na-toolchain-e-edicao-de-manifest.md) (dados vs. edição),
  [#16](https://github.com/loxia-lang/loxia/issues/16)
- **Implementação:** `loxia_core/execution/fs_runtime.py`,
  `loxia_core/execution/primitives.py`, `runtime/kernel.c`, `runtime/lox_runtime.h`,
  `std/fs.lx`, `std/results.lx`, `loxia/builtins_docs.py`,
  `tests/test_std_t2.py`, `tests/test_backend.py`, `tests/test_primitives.py`

## Contexto

O IO de arquivo era o único buraco assimétrico da stdlib: processos já tinham handles com
`read`/`write`/`close` ([ADR-0095](0095-processos-streams-poll.md)), mas arquivo só tinha
“leia tudo”/“escreva tudo” (`io.readFile`/`io.writeFile`). O sintoma mensurável era
`std.fs.appendText`: lê o arquivo inteiro e reescreve — O(n²) para log incremental — e não
havia como processar um arquivo grande por partes.

Ao mesmo tempo, o modelo de erro de host estava dividido: `framing`/`documents`/`jsonrpc`
usam `Result[T, *Failure]`, enquanto `fs.*` usava `T?`/`Bool` e `proc.*` usava `Int`/`Bool`.
`T?`/`Bool` perdem a causa: “não achei”, “sem permissão” e “é um diretório” viram o mesmo
`nil`. Em `proc.run`, o mesmo `nil` significava falha de spawn **ou** timeout.

Requisito de kernel: handles de arquivo exigem `open`/`read`/`write`/`close`, mas o kernel
já tinha os helpers de UTF-8 e o padrão de tabela de handles do `proc`; nenhuma primitiva
nova de SO além dessas quatro.

## Decisão

### 1. Falha de host é `Result[T, <Domínio>Error]`

| Situação | Forma |
| --- | --- |
| operação de host pode falhar (IO, processo, rede) | `Result[T, FileError/ProcError/...]` |
| pergunta booleana (`exists`, `kill`) | `Bool` |
| ausência que não é erro (`getenv` sem variável) | `T?` |
| parse de texto | `Result[T, ParseError]`; `T?` só em API legada com `parseResult` ao lado |
| kernel (baixo nível) | `Int`/`Bool`/`nil`; a camada ergonômica é a stdlib |

`kind` é um token estável (`notFound`, `permission`, `isDirectory`, `closed`, `badMode`,
`io`, …), **nunca** `strerror`/locale: a mensagem é determinística (I3) e a causa é
testável. A primitiva do kernel levanta `RuntimeError` com `"<kind>: <detalhe>"`; o wrapper
em Lox converte em `Result` sem estado global (`errno` não vaza para a linguagem).

### 2. `fs.open`: quatro primitivas, handle `Int`

- `fs.open(path, mode) -> Int` (1-based; falha levanta), `fs.read(id, n) -> String?`
  (`nil` = EOF, sempre em fronteira UTF-8), `fs.write(id, text) -> Nil`,
  `fs.close(id) -> Nil` (**idempotente**).
- Modos: `r`, `w` (trunca/cria) e `a` (cria/anexa); `appendText` deixa de ser O(n²).
- Sem finalizer: o handle é fechado explicitamente (`finally`/`withOpen`); a tabela vive no
  interpretador, não em global. Handle fechado usado depois é erro; fechar de novo não é.
- `--sandbox` nega as quatro primitivas (a lista acompanha `SANDBOX_DENIED_NAMES`).

### 3. Sem sintaxe `with`/`defer`

`std.fs.withOpen[T](path, mode, body) -> Result[T, FileError]` faz `try/finally` e devolve o
valor do corpo; o handle nunca escapa. Cobre saída normal, `return` e exceção — a mesma
garantia de `with`. `defer` só compraria estética: o único caso que ele resolve e o
callback não é `break`/`continue` de um laço externo, e handle que sobrevive à chamada
(writer de vida longa) precisa de `open` + `close` explícito em qualquer um dos dois.

### 4. Fora de escopo (explícito)

`seek`/`tell`, modos `r+`/`w+`/`a+`, `flush` (com `write(2)` cru não há buffer de usuário) e
binário/`Bytes` (tipo novo: `ValueType`, `Ty`, boxing no LLVM, checker). O acesso aleatório
interage com o buffer de fronteira UTF-8 — `seek` teria que invalidá-lo e `tell` precisaria
de duas definições (lógico vs. físico). Gatilhos para reabrir, registrados em Ideas: leitor
de formato com acesso aleatório (ZIP/índice), leitura retomável por offset, edição no lugar,
e necessidade medida de buffer de escrita.

### 5. Migração breaking documentada

`fs.readText`/`readLines`/`writeText`/`appendText`/`listDir` passam a devolver `Result`
(quebra de assinatura na 1.1.0; sem bump de major por decisão do mantenedor, porque não há
consumidor externo). `proc` (Stream/Process/run/spawn) e `csv`/`timex` migram para o mesmo
padrão nesta série de PRs; `json.parse`/`csv.parse` mantêm o par `parseResult` quando
existir, e nenhuma API antiga permanece como wrapper duplicado.

## Consequências

### Positivas

- A causa da falha chega ao programa (`FileError.kind`), testável e estável.
- Append O(n²) → O(n); leitura incremental com fronteira UTF-8 segura.
- Um único padrão de erro de host na stdlib; `proc` deixa de ser outlier.
- Kernel cresce 4 primitivas, todas com a mesma ABI e teste diferencial do `proc`.

### Negativas / custos

- Breaking change na stdlib sem major novo: documentada no CHANGELOG e nos ADRs.
- Quatro primitivas a mais (29 → 33) e uma cópia do helper `utf8_complete_prefix`
  compartilhada com `proc.c`.
- Mensagens de erro do kernel precisam ser strings estáticas: `lox_panic` guarda o ponteiro
  numa exceção catchable, então buffer de pilha vira dangling pointer (lição registrada no
  código).
- `withOpen` aloca uma closure por uso; irrelevante para IO, mas é diferente de `with`.

### Neutras

- Handles são `Int` até existir tipo opaco; a casca (`File`) muda sem mudar o usuário.
- `exists` continua `Bool` de propósito, apesar de “perder a causa”: é pergunta.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só `appendText`/`readSlice` (sem handles) | resolve append, mas cada chamada reabre e não há writer bufferizado nem `withOpen` |
| Handles completos agora (`seek`/`tell`/`+modos`) | complexidade de offset × buffer UTF-8 sem consumidor; gatilhos em Ideas |
| Sintaxe `with`/`defer` | ADR-0066; ganho marginal com closures + `finally` |
| Manter `T?`/`Bool` e só documentar | perde a causa e mantém três padrões |
| Wrapper legado + API nova em paralelo | duas superfícies para a mesma operação; a migração é barata porque não há consumidor |

## Como verificar

- `tests/test_std_t2.py`: escrita/leitura/append/listagem com `Result`, `notFound`, `io`.
- `tests/test_backend.py::test_std_fs_nativo`: diferencial native × interpreted com
  `withOpen`, `read(n)`, close idempotente e UTF-8.
- `tests/test_primitives.py`: as quatro primitivas na lista da sandbox.
- `tests/test_stdlib_docs.py`: docs geradas de `std.fs` e das primitivas.

## Referências

- Issue [#16](https://github.com/loxia-lang/loxia/issues/16).
- [ADR-0095](0095-processos-streams-poll.md) — handles `Int`, tabela 1-based, sem finalizer.
- [ADR-0072](0072-stdlib-batteries.md) — stdlib = Lox puro sobre o kernel.
- [ADR-0118](0118-toml-na-toolchain-e-edicao-de-manifest.md) — edição de arquivo vs. dados.
