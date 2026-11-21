# ADR-0120 — Localização de falha em exceções capturadas (`e.site`)

- **Status:** accepted (implementado)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0096](0096-testes-biblioteca-e-runner.md) (runner e
  `std.test`), [ADR-0089](0089-stack-trace-de-runtime.md) (trace de runtime),
  [ADR-0042](0042-excecoes.md) (exceções), [ADR-0014](0014-identidade-e-invariantes.md)
  (I1–I3), issue [#11](https://github.com/loxia-lang/loxia/issues/11)
- **Implementação:** `loxia_core/execution/lox_exception.py`,
  `loxia_core/execution/interpreter.py`, `loxia_core/semantics/checker.py`,
  `loxia_core/backend/lower_exceptions.py`, `runtime/core.c`,
  `runtime/lox_runtime.h`, `std/test.lx`, `loxia/test_runner.py`,
  `tests/test_std_test.py`, `tests/test_backend.py`

## Contexto

O [ADR-0096](0096-testes-biblioteca-e-runner.md) §7 adiou a localização de falha: o
relatório do `loxia test` aponta **arquivo + nome do teste + mensagem**, mas não a linha
do `expect`. A causa é estrutural: `Suite.it` captura a exceção com
`except Exception as e`, e o valor `LoxExceptionValue` só carrega `message`. O trace do
[ADR-0089](0089-stack-trace-de-runtime.md) é congelado no ponto mais interno, mas uma
exceção **capturada** não o carrega — o ADR-0089 §7 declara essa limitação explicitamente.

O sintoma é concreto: `t.expect(1 + 1).toBe(3)` produz `expected 3, got 2`, mas a
mensagem aponta para o `raise` dentro de `std/test.lx`, não para a linha do teste. Sem
essa linha, o relatório do runner não fecha o item 3 do #11.

Restrições:

1. **I1**: o tree-walk é o oráculo; o binário precisa produzir a mesma string.
2. **I3**: nada de caminho absoluto, endereço, PID ou timestamp na saída.
3. Sem sintaxe nova; `e.site` é um campo, não uma construção da linguagem.
4. A captura não pode custar no caminho feliz (só no `throw`/construção).

## Decisão

**Expor `e.site: String` em `Exception`, com `arquivo:linha:coluna` relativo, capturado
no ponto do `throw` a partir do frame do chamador.**

`site` é `""` quando não há posição (exceção criada sem frame, fonte ausente). É um campo
escalar — não é uma lista de frames e não altera o trace do ADR-0089.

### 1. O que exatamente é capturado

- **Exceção de usuário** (`raise TestFailure(...)`): o site é o **call site do frame
  atual** — para `toBe`, a linha do `expect(...).toBe(...)` no arquivo de teste. É o
  ponto que o relatório precisa.
- **Erro de runtime capturado como `RuntimeError`**: o site é o token do erro
  (`1 // 0`), porque é isso que o tree-walk já tem e o panic do binário já carrega.
- **`raise;` / `raise e`**: reemitem a partir do ponto do `raise`; o site é atualizado
  para esse ponto (mesma regra do trace no ADR-0089).
- **Exceção construída mas não lançada**: `site` é `""` (sem frame de throw); o valor
  só ganha posição quando é lançado.

### 2. Formato

`arquivo:linha:coluna`, com o arquivo relativo ao CWD (a mesma regra de I3 dos
diagnósticos). Quando a posição é sintética (`line == 0`/`column == 0`) ou o arquivo é
desconhecido, `site` é `""`; o chamador decide como exibir. Não há prefixo `at ` no valor:
a apresentação é do `std.test`/runner.

Exemplo:

```text
not ok 1 - grupo / falha
  # at tests/foo_test.lx:7:5
  # expected 3, got 2
```

### 3. Tree-walk

- `LoxExceptionValue` ganha `site: str = ""`.
- `LoxExceptionClass.call` captura `interpreter.current_site()`, que usa o frame mais
  interno (`_frames[-1].call_file/line/column`) e, sem frame, o `_call_site` atual.
- `LoxExceptionValue("RuntimeError", ...)` no `visit_try_stmt` usa o token do
  `LoxRuntimeError` (posição do erro, não do `try`).
- `visit_get` de `e.site` devolve a string (como `e.message`).
- O checker adiciona `site: String` aos campos de `Exception`; `e.site` fica tipado e
  `--check` continua limpo.

### 4. Backend

- `Exception` sintética ganha o campo `site` (índice 1, `String`); o layout e o bitmap
  já suportam campos extras.
- `_ctor_body` de exceção sintética grava `lox_exception_site()` no campo.
- `_raise` grava o site do frame atual no valor antes de `lox_throw`.
- `_bind_handler_exception`, ao materializar um `RuntimeError` de panic, grava
  `lox_exception_site_at(exception)` (arquivo/linha/coluna do panic) no campo.
- `runtime/core.c` expõe:
  - `void *lox_exception_site(void)`: formata o call site do frame atual;
  - `void *lox_exception_site_at(const void *exception)`: formata `file:line:column` do
    `LoxException` do panic.
  As duas devolvem uma `LoxStr` (mesmo `lox_str_from_cstr` já usado pelo runtime) e não
  imprimem nada; I3 fica na formatação (path relativo, sem endereço).

### 5. `std.test` e runner

- `std.test` já captura `except Exception as e`; passa a incluir
  `e.site` no protocolo (`"location": {file,line,column}`) e, no TAP humano, uma linha
  `  # at <site>` antes da mensagem.
- O runner converte `location` em `tests[].location` no JSON v1 (campo já previsto, hoje
  `null`).
- `e.site` não muda a mensagem de erro nem o exit code; só acrescenta relatório.

### 6. O que **não** entra

- Lista completa de frames (`e.trace`). O ADR-0089 já tem o trace no ponto do panic; expor
  frames em exceção capturada é um passo maior (lista/ABI) e não é necessário para a linha
  do `expect`.
- `e.site` como objeto/estrutura; string escalar é suficiente e barata.
- `source`/caret no binário: o binário pode rodar sem a fonte; o campo é posição, não
  trecho.

## Consequências

### Positivas

- Fecha o item 3 do #11 com o menor custo de ABI: um campo `String` por exceção.
- `std.test` e o runner ganham linha sem duplicar parser de fonte nem reflection.
- Mantém I1: a string é montada da mesma forma nos dois motores, com path relativo.
- Reutilizável por `Result`/logs futuros sem um segundo modelo de trace.

### Negativas / custos

- Toda exceção passa a carregar uma string (alocação no `throw`); exceções como controle
  de fluxo pagam esse custo.
- O backend ganha um campo sintético e duas funções de runtime; o layout da exceção muda.
- `e.site` é uma posição, não a pilha: um helper que lança a exceção pode deslocar o site
  para o helper (o frame do chamador), o que é o comportamento desejado para o `expect`,
  mas precisa ser documentado.
- Exceções construídas sem frame ficam com `""`; o relatório não inventa linha.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Não expor nada e mapear nome do teste → linha do `it` no runner | Só dá a declaração do teste, não a linha do `expect`; falha em helpers. |
| `e.trace: List[String]` | Mais superfície e ABI; o `expect` só precisa da posição mais interna. |
| `e.trace: List[Frame]` (estruturado) | Melhor para tooling, mas exige classe/list nos dois motores e mexe no trace do ADR-0089. |
| Guardar a posição como três campos `Int`/`String` (`e.file`/`e.line`/`e.column`) | Mais campos públicos e mais validação no checker; uma string formatada é suficiente para o relatório e para logs. |
| Expor o trace inteiro no `std.test` via `LoxRuntimeError` | O valor capturado é `LoxExceptionValue`, não o erro interno; expor isso vazaria a implementação. |

## Como verificar

- `tests/test_std_test.py`: `e.site` de `t.expect` aponta para a linha do teste e não para
  `std/test.lx`; `e.site` de `RuntimeError` capturado aponta para a linha do erro.
- `tests/test_test_runner.py` + `tests/test_test_runner_schema.py`: `tests[].location`
  preenchido no JSON e `# at ...` no TAP.
- `tests/test_backend.py`: caso novo no corpus (`LEVELS`) comparando stdout/stderr/exit
  nos três canais; o binário e o tree-walk imprimem o mesmo `site`.
- `tests/test_checker.py`: `e.site` tipado como `String` e `--check` limpo.
- `make check-fast` e `make check` verdes.

**Critério para revisitar:** necessidade de mais de uma posição (helpers/stack) ou de
estrutura para tooling; aí `e.trace` completo vira ADR próprio.
