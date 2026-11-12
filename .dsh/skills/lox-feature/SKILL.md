---
name: lox-feature
description: Procedimento end-to-end para adicionar ou alterar uma feature da linguagem (token, nó de AST, parser, interpreter, AstPrinter e testes) neste interpretador Lox.
whenToUse: Ao implementar nova sintaxe, operador, statement ou nó de AST; ao mudar semântica de algo que já existe.
---

# Feature de linguagem, de ponta a ponta

## Antes de tocar em código

1. `make check` precisa estar verde. Se não estiver, conserte a base primeiro.
2. **Passe a feature pelo portão de admissão** ([`docs/adr/0014-identidade-e-invariantes.md`](../../../docs/adr/0014-identidade-e-invariantes.md)):
   não viola I1–I3 (equivalência, nada implícito, determinismo), cabe na semântica que o
   LLVM reproduz (ou tem plano verificável), a ausência dói de verdade e existe teste que
   a policia. Feature bonita que só compra superfície = dívida paga pelo codegen.
3. Escolha **um** comportamento observável e escreva o caso antes do código:
   `tests/cases/<nome>.lox` com `# expect: ...` (ver skill `lox-testing`).
4. Feature que muda gramática → registrar em `TODO.md` §1. Escolha de rumo da
   linguagem → registrar em `TODO.md` §11 **antes** de implementar.
5. Nunca implemente um capítulo futuro do livro "de passagem" (ex.: funções antes do
   cap. 10). Ver `AGENTS.md` §8.

## Ordem de implementação

| # | O quê | Onde |
|---|-------|------|
| 1 | Token / keyword | `src/frontend/token_type.py`, `src/frontend/keywords.py` |
| 2 | Lexema (símbolo novo) | `src/frontend/scanner.py::_scan_token` |
| 3 | Nó de AST | `src/frontend/expr.py` ou `src/frontend/stmt.py` — `@dataclass(frozen=True)` herdando de `Expr`/`Stmt` |
| 4 | Método no `Visitor` | mesmo arquivo (`visit_<no>_expr` / `visit_<no>_stmt`) |
| 5 | `accept` | mesmo arquivo |
| 6 | Parsing | `src/frontend/parser.py` (respeite a cascata de precedência do `AGENTS.md` §3) |
| 7 | Semântica | `src/execution/interpreter.py` |
| 8 | Debug | `src/frontend/ast_printer.py` — todo nó precisa de `visit_*`, senão o dump quebra |
| 9 | Teste | `tests/cases/` + unitário se a lógica interna for não trivial |
| 10 | Docs | `docs/spec/` (comportamento) e ADR em `docs/adr/` se for decisão; marque no `TODO.md` |

## Invariantes que não podem quebrar

- Números são `Int` (i64) e `Float` (f64), **separados** ([ADR-0006](../../../docs/adr/0006-int-float-separados.md)).
  Em checagem numérica use `src.execution.numeric.is_number`/`is_int`; nunca
  `isinstance(x, (int, float))` direto — `isinstance(True, int)` é `True`.
- Saída e diagnóstico são **determinísticos** (I3): nada de endereço, PID, timestamp,
  caminho absoluto ou ordem de `set`/`dict`. `tests/test_determinism.py` policia.
- `nil` é `None` — nunca use sentinela própria.
- Truthiness: só `nil` e `false` são falsos.
- Stringify vem de `src/execution/values.py::stringify`; não duplique formatação.
- Erro de sintaxe → `self.reporter.error(...)` + `ParseError`; erro de runtime →
  `raise LoxRuntimeError(token, msg)`. O reporter vem por injeção.
- Imports sempre `from src.x import Y` (nunca `from x import Y`).
- O `ErrorReporter` é por execução (nunca volte a criar estado de classe).

## Definition of Done

- [ ] Caso golden novo passa (`make test`).
- [ ] `make lint` e `make type` verdes.
- [ ] `AstPrinter` cobre o nó novo (teste de parser, se possível).
- [ ] Mensagem de erro no estilo do livro (`Expect ';' after value.`).
- [ ] Sem regressão: suíte inteira verde.
- [ ] Se mudou comportamento: `docs/spec/` atualizado; decisão de design → ADR em `docs/adr/`.
- [ ] `tests/test_determinism.py` verde (nada volátil na saída).

## Armadilhas

- Mudar precedência sem teste de AST: escreva o caso `(1 + 2) * 3` antes.
- Esquecer o `accept`: o nó existe, mas o visitor nunca é chamado.
- Implementar no `Interpreter` sem adicionar ao `Visitor`: o `mypy` (strict) acusa.
- Usar `print()` para debug no `src/`: use o REPL ou o `AstPrinter`.
