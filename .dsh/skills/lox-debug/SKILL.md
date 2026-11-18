---
name: lox-debug
description: Triagem de falhas no interpretador — isolar caso mínimo, inspecionar tokens e AST, localizar a camada culpada e fechar com teste de regressão.
whenToUse: Quando um script .lx falha, um caso da suíte quebra ou o comportamento diverge do esperado.
---

# Depurar um bug

## 1. Reproduza isolado

```bash
uv run python -m tests.runner <filtro>   # ex.: undefined, block, for
uv run main.py caminho/caso.lx           # veja stdout/stderr reais
```

Se não houver caso, **reduza** o script até o mínimo que ainda falha (uma linha é
ideal). Bug sem reprodução mínima costuma virar dois bugs.

## 2. Localize a camada

| Sintoma | Camada provável | Como inspecionar |
|---|---|---|
| `ModuleNotFoundError` | imports | `uv run python -c "import loxia_core.execution.interpreter"` — imports são `from loxia_core.x` |
| erro de sintaxe inesperado | scanner/parser | `python -c` com `Scanner(src).scan_tokens()`; veja lexemas e linhas |
| AST errada (precedência) | parser | `AstPrinter().print(expr)` em `python -c` |
| `Undefined variable` indevido | `Environment` | lembre: `get` procura no escopo atual **antes** do `enclosing` |
| valor estranho impresso | `stringify` / sentinela | `var x;` deve virar `None`, não `object()` |
| erro só no REPL | `Parser(repl=...)` | no REPL o `;` final é opcional; fora dele é obrigatório |

## 3. Suspeitas que já morderam este repo

- a negação (`!`, hoje `not`) retornava a truthiness em vez de negá-la.
- `Environment.get/assign` procuravam no escopo errado (blocos/`for` quebravam).
- `ErrorReporter` global de classe — hoje é instância por execução; não recrie o padrão.
- `bool` sendo aceito como número (`isinstance(True, int)` é `True` em Python).
- `AstPrinter` sem `visit_*` de um nó que o parser já produz (ex.: `Logical`).

## 4. Feche o ciclo

1. Escreva o caso golden que falha **antes** do fix.
2. Corrija a causa, não o sintoma.
3. `make check` completo (lint, mypy strict, pytest).
4. Se o fix muda comportamento visível, atualize `docs/spec/` (e a issue/roadmap se for
   algo planejado).
5. Commit `fix: <sintoma>` com o caso de regressão junto.

## Ferramentas úteis

- `parser.reporter.silent = True` silencia erros de sintaxe (usado pelo REPL); o
  `parse_repl` restaura sozinho, mas se mexer nisso devolva para `False`.
- `uv run python -m loxia_core.frontend.ast_printer` roda o exemplo do cap. 6 e valida o printer.
- `git bisect` + `make test`: a suíte é rápida (<2 s), dá para bisectar à vontade.
