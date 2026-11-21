# ADR-0126 — Módulo nativo embutido: SQLite

- **Status:** proposed
- **Data:** 2026-11-21
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0071](0071-primitivas-de-runtime.md) (kernel sem FFI genérica),
  [ADR-0072](0072-stdlib-batteries.md) (std = Lox puro), [ADR-0079](0079-stdlib-t2.md) /
  [ADR-0095](0095-processos-streams-poll.md) (handles), [ADR-0119](0119-fs-open-handles-e-erro-de-host.md)
  (erro e sandbox), [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) (orçamento),
  [ADR-0125](0125-bytes-tipo-binario.md) (BLOB), [ADR-0127](0127-pacotes-com-codigo-nativo.md)
  (pacotes nativos), [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md) (bundle),
  [ADR-0105](0105-dependencias-git.md) (lock)
- **Implementação:** `vendor/sqlite/sqlite3.c` + `sqlite3.h` (amalgamation pinada),
  `runtime/sqlite.c`, `loxia_core/execution/sqlite_runtime.py`,
  `loxia_core/execution/primitives.py` (`NATIVE_MODULE_PRIMITIVES`),
  `loxia_core/backend/driver.py` (`runtime_units(imports)`), `bundled/sqlite.lx`,
  `loxia_core/bundle.py`, `loxia_core/loader/loader.py`, `tests/cases/sqlite/*.lx`

## Contexto

SQLite é uma **biblioteca + formato de arquivo**, não um servidor. A distribuição oficial é
a *amalgamation* (`sqlite3.c` + `sqlite3.h`, domínio público), feita para ser embutida; é o
que o próprio CPython faz no módulo `sqlite3` (linkando a libsqlite3 do sistema ou a
empacotada). Reescrever SQL em Lox seria absurdo: ~250 mil linhas e décadas de testes.

O Loxia hoje não tem onde colocar isso:

- `std/` é **Lox puro sobre o kernel** ([ADR-0072](0072-stdlib-batteries.md)); SQLite é C.
- O kernel é tabela fixa de **primitivas de host** com orçamento ([ADR-0123](0123-orcamento-do-kernel-por-grupo.md));
  `sqlite.open`/`prepare`/`step` não são SO nem representação, e 19 slots estourariam o teto.
- O runtime compila **sempre** as 7 unidades ([`driver.py#L39-L48`](../../loxia_core/backend/driver.py));
  jogar `sqlite3.c` ali faria todo binário pagar ~1 MB.
- Pacotes são **só `.lx`**: o manifest aceita apenas `package`/`modules`/`dependencies` e o
  lock hasheia só `.lx` ([`deps.py#L48-L68`](../../loxia_core/loader/deps.py)). Pacote nativo
  é o [ADR-0127](0127-pacotes-com-codigo-nativo.md), adiado.

Falta uma camada: **módulo nativo embutido**, que viaja com o compilador, entra só quando
importado e não é `std`.

## Decisão

### 1. Quarta camada: módulo nativo embutido, fora de `std/`

| Camada | O que é | Onde |
| --- | --- | --- |
| kernel | primitivas de host, orçamento próprio | `primitives.py` + `runtime/*.c` |
| std | Lox puro sobre kernel/nativos | `std/*.lx` |
| **módulo nativo** | C + wrapper Lox, **opt-in por `import`** | `vendor/<lib>/` + `bundled/*.lx` |
| pacote | Lox (e, um dia, nativo) de terceiro | repo + `git` dep |

- O bundle ganha a raiz `bundled/` (reservada, ao lado de `std/`), com as mesmas regras:
  sem sombreamento pelo projeto, `_` privado, ciclo é erro.
- `std/` continua Lox puro; `std` pode chamar primitivas do kernel (já faz), mas **não**
  módulo nativo. Quem quiser a API ergonômica importa `sqlite`.

### 2. Dois nomes, um módulo

- **`sqlite3`** — namespace primitivo (baixo nível): handles, `Result` não; erro é
  `RuntimeError("<kind>: <msg>")` com site. É o espelho da ABI C.
- **`sqlite`** — módulo Lox em `bundled/sqlite.lx` (alto nível): `Db`, `Statement`, `Row`,
  `DbError`, transações, iteração, `Result`. É o que o programa importa.

Nomes diferentes de propósito: `import sqlite` não sombreia o namespace `sqlite3`, e o
módulo Lox pode usar o namespace sem auto-referência (o mesmo padrão de `io`/`std.io`).
Regra de nomeação: namespace bruto = nome da biblioteca (`sqlite3`, `pq`); módulo público =
nome curto (`sqlite`, `pg`).

### 3. Superfície (namespace `sqlite3`, orçamento de módulo)

Handles `Int` 1-based, tabela no interpretador, `close` idempotente, uso depois de fechar é
`RuntimeError`, **sem finalizer** (Boehm — [ADR-0119](0119-fs-open-handles-e-erro-de-host.md)).

| Grupo | Primitivas |
| --- | --- |
| conexão | `open(path) -> Int`, `close(id)`, `errmsg(id) -> String`, `changes(id) -> Int`, `lastInsertRowid(id) -> Int` |
| statement | `prepare(db, sql) -> Int`, `finalize(stmt)`, `reset(stmt)`, `step(stmt) -> Int` (0 = fim), `columnCount(stmt) -> Int` |
| bind | `bindInt(stmt, i, v)`, `bindFloat(stmt, i, v)`, `bindText(stmt, i, s)`, `bindNull(stmt, i)`, `bindBytes(stmt, i, b)` (após [ADR-0125](0125-bytes-tipo-binario.md)) |
| column | `columnInt`, `columnFloat`, `columnText`, `columnBytes`, `columnIsNull(stmt, i) -> Bool` |

19 primitivas, orçamento de módulo **20** (`NATIVE_MODULE_BUDGET`), **fora** dos 40 do
kernel. O teste de orçamento do [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) cobre as
duas tabelas.

### 4. Link condicional: o binário só paga se importar

- `RUNTIME_NAMES` deixa de ser constante: `runtime_units(imports)` devolve as unidades base
  + a unidade do módulo nativo importado (`sqlite.c` + `vendor/sqlite/sqlite3.c`).
- A chave do cache de build passa a incluir o conjunto de unidades e a versão do vendor.
- Teste: programa sem `import sqlite` **não** tem os símbolos `sqlite3_*` no binário
  (`nm`/`strings`); programa com import tem, e o tamanho cresce de forma mensurável.
- `--emit=ll`/`obj` não linkam; `--emit=exe` linka só o selecionado.

### 5. Vendorização e flags determinísticas

- `vendor/sqlite/sqlite3.c` + `sqlite3.h` da versão pinada (registrada em
  `vendor/sqlite/VERSION` e no `CHANGELOG.md`), com SHA-256 no repositório.
- Flags fixas (sem descoberta de ambiente): `-DSQLITE_THREADSAFE=0`
  (a linguagem é single-thread), `-DSQLITE_OMIT_LOAD_EXTENSION`, `-DSQLITE_DQS=0`,
  `-DSQLITE_OMIT_DEPRECATED`, `-DSQLITE_DEFAULT_FOREIGN_KEYS=1`; **sem** ICU, FTS, JSON1
  (JSON1 pode entrar depois; ICU traz locale e mata o I3).
- Atualização: release de segurança do SQLite dispara bump + nota no CHANGELOG; o lock não
  se aplica (é código do toolchain, não dependência de projeto).
- Se o usuário preferir a lib do sistema, fica como flag de build futura (`--system-sqlite`),
  não como default: a versão empacotada é o contrato reprodutível.

### 6. ABI e erros

- O C usa a ABI do runtime (`LoxValue`, `LoxStr`, `LoxBytes`); nada de `extern fn`.
- **API pull na v1**: `prepare` → `step` → `column`. Callback C→Lox só com guarda (§6.1), e
  como capacidade **native-only** ([ADR-0128](0128-contrato-de-motores.md)); na v1 não há
  `exec(sql, fn)` nem UDF.
- Código de retorno → `RuntimeError("<kind>: <msg>")` no primitivo, com `kind` estável
  (`busy`, `locked`, `constraint`, `notFound`, `misuse`, `io`, `corrupt`, `readOnly`,
  `range`, `unknown`); a mensagem do SQLite não é contrato e não entra no I3 (o programa é
  ambient de qualquer forma).
- O módulo Lox converte para `DbError { kind: String, message: String }` e devolve `Result`.

### 6.1 Callbacks: por que não na v1, e a forma segura

O runtime lança com `setjmp`/`longjmp` ([`core.c#L388-L422`](../../runtime/core.c)): o
`raise` pega o `LoxTryFrame` corrente e salta para ele. Um callback chamado de dentro de C
que lance, portanto, **atravessa os frames da biblioteca**:

```
fn main() {
  try { sqlite3.exec(db, "select ...", cb) }   <- alvo do longjmp
             │
             └─ C: sqlite3_exec ──── cb ──── closure Lox
                                          │ raise
                                          └─ longjmp ───────► pula sqlite3_exec inteiro
}
```

Em C não há destrutor: `sqlite3_finalize` não roda, o mutex não é solto, a transação fica
pela metade e o `exec` nunca retorna. É a mesma razão pela qual o SQLite documenta que o
callback não pode fazer `longjmp`, e pela qual Lua usa `lua_pcall` e Rust aborta panic
atravessando `extern "C"`.

A forma segura é um **guarda na fronteira**, e não uma proibição de callback:

```
shim(cb, ctx):
  frame = lox_try_push()
  if (setjmp(lox_try_buffer(frame)) == 0) {
      valor = lox_call(cb, ctx)          # pode lançar
  } else {
      guarda_erro(handle, frame)          # exceção capturada AQUI
      lox_try_pop(frame)
      return ABORT_SENTINEL                # 1 para sqlite3_exec
  }
  lox_try_pop(frame)
  return OK
```

- Depois do retorno C (`SQLITE_ABORT`), o primitivo relança em Lox no ponto da chamada: a
  exceção nunca cruzou C.
- UDF (`create_function`): o shim chama `sqlite3_result_error(ctx, msg, -1)` e retorna
  normalmente — não existe código de retorno de erro nesse caminho.
- A closure fica viva num registro por handle até `close`/`unregister` (sem finalizer).
- O shim assume **thread única** e checa a profundidade: estouro vira erro, não panic.

Custo: um `LoxTryFrame` por invocação (hoje `lox_try_push` aloca; um guarda na pilha seria
melhor no futuro) e a contabilidade de lifetime. Por isso callbacks ficam **fora da v1**:
o pull cobre o caso comum, e o guarda entra quando houver consumidor de verdade (UDF,
`exec` com callback, `libpq` notice). O guarda é trabalho de **runtime**, não de SQLite, e
é reutilizável por todo módulo nativo.

### 7. Tipos e SQL

- `Int` ↔ INTEGER, `Float` ↔ REAL, `String` ↔ TEXT (UTF-8), `nil` ↔ NULL,
  `Bytes` ↔ BLOB (só depois do [ADR-0125](0125-bytes-tipo-binario.md)).
- Sem coerção implícita (I2): o `bind` é explícito por tipo; coluna lida com o getter do
  tipo esperado, e divergência é erro (não "converte se der").
- O checker **não tipa SQL**: a linha é dinâmica (`Row.getInt(i)`, `Column`), com `Result`
  no acesso. Tipar SQL exigiria schema e um parser de SQL — não-objetivo.

### 8. Ambiente, sandbox e testes

- `sqlite3` é **ambient**: fora do corpus I1/I3, como `fs`/`proc`. Testes usam banco de
  fixture em diretório temporário e não imprimem caminho absoluto, mtime nem rowid instável.
- `--sandbox` nega `sqlite3.*` (entra na lista de negação, como `fs.open`), com teste.
- Teste de contrato: handle fechado usado de novo é erro; `close` duas vezes não é; `step`
  depois do fim é `0`; erro de constraint devolve `Result.Err` com `kind = "constraint"`.

## Consequências

### Positivas

- Banco de dados real sem reescrever SQL nem inventar formato.
- Prova a camada nativa (link condicional, vendor, sandbox) antes de pacotes de terceiro.
- BLOB chega junto com `Bytes`; TEXT/INTEGER/REAL já funcionam sem ele.
- Um binário que não importa `sqlite` não paga nada.

### Negativas / custos

- ~250 mil linhas de C vendorizadas no repositório (+~1 MB no binário que usa, +tempo de
  build).
- Ciclo de CVE próprio: agora o Loxia atualiza SQLite, não só o Python.
- `RUNTIME_NAMES` vira função do grafo de imports: mais um eixo no cache e nos testes.
- Raiz `bundled/` nova no loader e no wheel.
- API dinâmica: o checker não ajuda em SQL; o erro aparece em runtime.
- Sem callback na v1 a API fica só pull: UDF e `exec(sql, fn)` esperam o guarda (§6.1).
- Callback guardado é **native-only** ([ADR-0128](0128-contrato-de-motores.md)): o
  interpretador recusa, então programas com UDF não rodam em `loxia run`.
- SQLite é portátil, mas o runtime como um todo é POSIX-first; Windows continua fora.

### Neutras

- `std/` não muda; `std` não importa `sqlite`.
- O nome `sqlite3` é feio, mas é o nome da biblioteca e evita sombreamento.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Reescrever SQL em Lox | ~250 mil linhas e décadas de testes; não é o papel da linguagem. |
| Colocar no kernel como primitivas normais | 19 slots estouram o teto e não é SO/representação; o kernel viraria catálogo de bibliotecas. |
| `std.sqlite` | `std` é Lox puro; e a promessa de 5 anos da stdlib não combina com API de banco em evolução. |
| Linkar a libsqlite3 do sistema por default | Deriva de versão e de flags entre máquinas; quebra reprodutibilidade. Fica como opção futura. |
| FFI genérica (`extern fn`) | [ADR-0071 §4](0071-primitivas-de-runtime.md): ABI, ownership e portabilidade sem retorno; e o interpretador perderia a independência. |
| Esperar pacotes nativos ([ADR-0127](0127-pacotes-com-codigo-nativo.md)) | Bloqueia o caso concreto; o embutido é o degrau que valida a infraestrutura. |

## Como verificar

- Golden `tests/cases/sqlite/*.lx`: criar/inserir/selecionar, transação, erro de constraint,
  `close` idempotente, uso após `close`, `changes`/`lastInsertRowid`, `NULL`, BLOB (após
  `Bytes`).
- Teste de build: `nm` no binário sem e com `import sqlite` (símbolos ausentes/presentes);
  cache de build muda de chave quando o vendor muda.
- Sandbox: `import sqlite` negado com a mensagem padrão.
- `make bench`: laço de 10k inserts/seleções contra baseline (para não regredir o caminho).
- `--check` limpo nos exemplos e I4 preservado (o backend só recusa o que não baixa).

Critério para revisitar: `Bytes` para BLOB (primeira extensão), segunda biblioteca (pg,
[ADR-0127](0127-pacotes-com-codigo-nativo.md)), SQLite no Windows, ou necessidade de FTS/ICU.

## Referências

- [SQLite amalgamation](https://sqlite.org/amalgamation.html) e licença de domínio público.
- [ADR-0071](0071-primitivas-de-runtime.md) — kernel e por que não FFI.
- [ADR-0119](0119-fs-open-handles-e-erro-de-host.md) — handles, `Result` e sandbox.
- [ADR-0125](0125-bytes-tipo-binario.md) — BLOB.
