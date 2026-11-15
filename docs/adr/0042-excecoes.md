# ADR-0042 — Exceções: classes, `try`/`except`/`finally` e `raise` no tree-walk

> **Atualizado por** [ADR-0078](0078-nome-loxia-extensao-lx.md): a classe embutida
> `LoxRuntimeError` passou a se chamar `RuntimeError`. O corpo abaixo é o registro histórico
> da decisão da época.

- **Status:** accepted (implementado no tree-walk; backend L6 pendente)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0026](0026-freeze-1.0.md), [ADR-0039](0039-decisoes-tipos-pendentes.md),
  [ADR-0041](0041-enums-match.md), [`../../TODO.md`](../../TODO.md) §11,
  [`../spec/semantica.md`](../spec/semantica.md)

## Contexto

A 1.0 tinha erro de runtime fatal e `Result` para erro esperado. Exceções (`try`,
`except`, `finally`, `raise`) ficaram como ideia pendente; o usuário decidiu implementá-las,
com backend adiado para o L6.

## Decisões

1. **Classes de exceção.** `Exception` é a base embutida; `LoxRuntimeError` é subclasse
   embutida. O usuário declara `class MyError(Exception) { init(msg: String) { this.message = msg } }`.
   `raise Expr` exige uma instância de `Exception`; `raise;` relança a exceção corrente
   dentro de `except`.
2. **Sintaxe de `try`/`except`/`finally`.** `try` é **statement**; `except Tipo as e` é
   tipado e pode repetir; `finally` é opcional; exige pelo menos um `except` ou `finally`.
   `except Exception as e` é o catch-all e precisa ser o último handler.
3. **Erros de runtime viram exceção genérica.** Qualquer `LoxRuntimeError` (divisão por
   zero, índice, campo, etc.) pode ser capturado como `LoxRuntimeError` no `try`; ele vira
   um valor `LoxRuntimeError` no boundary. Subclasses específicas (`DivisionByZero`,
   `IndexError`, ...) ficam para depois.
4. **`finally` e fluxo.** `finally` sempre roda; `return`/`raise` dentro dele vencem o
   fluxo anterior. `raise;` fora de `except` é erro.
5. **Uncaught.** Exceção não capturada vira erro fatal: `Unhandled exception: <tipo>: <msg>`
   + `[line N]`, exit 70. Sem stack trace/colunas.
6. **Backend.** `try`/`raise` são rejeitados com 65 até o L6 (unwinding/landing pads);
   o tree-walk é a spec até lá. I1 diferencial não cobre exceções ainda.
7. **Convivência com `Result`.** `try`/`raise` para falha excepcional; `Result` para erro
   esperado. Não há `throw` separado.

## Limitações da v1

- Sem exceções específicas de runtime (`DivisionByZero` etc.); todas são `LoxRuntimeError`.
- Sem stack trace, `else`, catch por enum/valor, múltiplos `except` do mesmo tipo ou
  exceções genéricas de usuário além de `Exception`.
- Exceções de usuário são classes; enums não são exceções.

## Alternativas rejeitadas

- **Só `raise` explícito capturável:** não pega divisão por zero; o usuário queria o
  comportamento Python-like.
- **Exceções como enums:** menos Python, exigiria `match` para o caso específico.
- **Erros específicos já na v1:** mapear todos os sites e a hierarquia é uma segunda fase.
- **Backend agora:** caro e fora do L4; fica no L6.
