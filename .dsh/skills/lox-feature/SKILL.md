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
   `tests/cases/<nome>.lx` com `# expect: ...` (ver skill `lox-testing`).
4. Feature que muda gramática → issue `decision` com `gate:syntax` (quatro perguntas do
   ADR-0066 e aprovação humana). Escolha de rumo da linguagem → issue `decision`/ADR
   **antes** de implementar; o que já foi adiado está no ADR-0107.
5. Nunca implemente um capítulo futuro do livro "de passagem" (ex.: funções antes do
   cap. 10). Ver `AGENTS.md` §8.

## Ordem de implementação

| # | O quê | Onde |
|---|-------|------|
| 1 | Token / keyword | `loxia_core/frontend/token_type.py`, `loxia_core/frontend/keywords.py` |
| 2 | Lexema (símbolo novo) | `loxia_core/frontend/scanner.py::_scan_token` |
| 3 | Nó de AST | `loxia_core/frontend/expr.py` ou `loxia_core/frontend/stmt.py` — `@dataclass(frozen=True)` herdando de `Expr`/`Stmt` |
| 4 | Método no `Visitor` | mesmo arquivo (`visit_<no>_expr` / `visit_<no>_stmt`) |
| 5 | `accept` | mesmo arquivo |
| 6 | Parsing | `loxia_core/frontend/parser.py` (respeite a cascata de precedência do `AGENTS.md` §3) |
| 7 | Semântica | `loxia_core/execution/interpreter.py` |
| 8 | Debug | `loxia_core/frontend/ast_printer.py` — todo nó precisa de `visit_*`, senão o dump quebra |
| 9 | Teste | `tests/cases/` + unitário se a lógica interna for não trivial |
| 10 | Docs | `docs/spec/` (comportamento) e ADR em `docs/adr/` se for decisão; feche a issue no PR |

## Invariantes que não podem quebrar

- Números são `Int` (i64) e `Float` (f64), **separados** ([ADR-0006](../../../docs/adr/0006-int-float-separados.md)).
  Em checagem numérica use `loxia_core.execution.numeric.is_number`/`is_int`; nunca
  `isinstance(x, (int, float))` direto — `isinstance(True, int)` é `True`.
- Saída e diagnóstico são **determinísticos** (I3): nada de endereço, PID, timestamp,
  caminho absoluto ou ordem de `set`/`dict`. `tests/test_determinism.py` policia.
- `nil` é `None` — nunca use sentinela própria.
- Truthiness: só `nil` e `false` são falsos.
- Nome embutido novo (prelúdio, checker, backend) **não** leva a marca da linguagem:
  `RuntimeError`, não `LoxiaError` ([ADR-0078](../../../docs/adr/0078-nome-loxia-extensao-lx.md)).
  Ao adicionar um nome, atualize os três pontos: `loxia_core/execution/prelude.py`
  (`BUILTIN_NAMES`), `loxia_core/semantics/checker.py` (classe pré-declarada) e o lowering.
- Stringify vem de `loxia_core/execution/values.py::stringify`; não duplique formatação.
- Erro de sintaxe → `self.reporter.error(...)` + `ParseError`; erro de runtime →
  `raise LoxRuntimeError(token, msg)`. **Atenção às camadas** (ADR-0078): essa é a classe
  **Python** interna; na linguagem ela aparece como `RuntimeError`. Não troque o `raise`
  para `RuntimeError` — isso levantaria o builtin do Python e furaria o contrato.
  O reporter vem por injeção.
- Imports sempre `from loxia_core.x import Y` (nunca `from x import Y`).
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
- Usar `print()` para debug no `loxia_core/`: use o REPL ou o `AstPrinter`.
