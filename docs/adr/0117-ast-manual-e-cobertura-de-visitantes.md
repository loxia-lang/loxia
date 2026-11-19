# ADR-0117 — AST manual: sem gerador de schema; cobertura pelo protocolo

- **Status:** accepted (implemented)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0004](0004-identidade-dos-nos-de-ast.md) (identidade dos nós),
  [ADR-0107](0107-adiados-e-nao-objetivos.md) (adiados), issue
  [#15](https://github.com/loxia-lang/loxia/issues/15)
- **Implementação:** `class AstPrinter(ExprVisitor[str], StmtVisitor[str])`,
  `class Variable(Expr)` e `tests/test_ast_hierarchy.py`.

## Contexto

A issue [#15](https://github.com/loxia-lang/loxia/issues/15) propõe gerar a AST e os
visitantes a partir de um schema, para não esquecer um `visit_*` quando um nó novo entra.
O próprio critério de pronto aceita a alternativa de manter manual com checklist.

O que existe hoje:

- **40 nós** (24 `Expr`, 16 `Stmt`) e **4 visitantes** (`Interpreter`, `Checker`,
  `Resolver`, `AstPrinter`) — 160 métodos `visit_*`.
- `Interpreter`, `Checker` e `Resolver` herdam `Visitor`; o mypy já exige todos os
  métodos deles. O `AstPrinter` era a exceção: não herdava o protocolo, então um nó novo
  só quebrava no runtime do `--dump-ast`.
- `Variable` estava fora da hierarquia `Expr` desde o primeiro AST. A correção histórica
  dos “nós fora da hierarquia” cobriu `Assign`/`Call`/`Get`/`Logical`/`Set`/`Super`/
  `This` e esqueceu `Variable`; era bug, não desenho.
- Um nó novo toca **9–15 arquivos**: parser, lowering, `lower_containers`, `captures`,
  LSP, symbols e docgen. O gerador cobriria dataclasses, protocols e `accept`, mas não
  parser, lowering nem LSP.

Um gerador teria custo real: schema/generator/testes/CI (~1–2 semanas), migração de 40
nós e helpers (`Param`, `Field`, `MatchArm`, patterns), defaults e forward references.
Além disso, o código gerado precisa preservar `@dataclass(frozen=True, eq=False)`
([ADR-0004](0004-identidade-dos-nos-de-ast.md)) e ser checked-in, com drift no CI. A
linguagem está congelada na 1.0; novos nós são raros. O ganho não paga o custo agora.

## Decisão

1. **Manter o AST manual.** Não há schema, codegen nem arquivo gerado nesta fase.
2. **`AstPrinter` herda os protocols** `Visitor[str]` de `expr` e `stmt`. O mypy passa a
   exigir os 40 métodos; remover a herança ou esquecer um `visit_*` quebra o type check.
3. **Todo nó concreto herda `Expr`/`Stmt`.** `Variable` foi corrigido para `Variable(Expr)`.
   `tests/test_ast_hierarchy.py` trava as duas invariantes (hierarquia dos nós e herança
   dos protocols pelo printer).
4. O checklist de nó novo continua no `AGENTS.md`/skill: dataclass, `Visitor`, `accept`,
   parser, interpreter, checker, resolver, `AstPrinter`, backend, teste.
5. **Gatilho para reabrir o gerador:** 3+ nós novos em um ciclo, um 5º visitante, ou um
   segundo consumidor que precise de metadados estruturais (traversal/serialização/LSP).
   Aí sim um ADR novo decide schema, geração e drift.

## Consequências

### Positivas

- A dor declarada (“esquecer um visitante”) fica coberta pelo mypy no `AstPrinter`, sem
  codegen e sem arquivo gerado.
- `Variable` volta à hierarquia; a inconsistência silenciosa não se repete.
- Identidade `frozen`/`eq=False`, IDE, debugging e revisão continuam simples.
- Zero custo de generator/schema/CI para um AST que muda pouco.

### Negativas / custos

- Adicionar um nó continua tocando parser, lowering e LSP manualmente; o gerador não
  reduz essa parte.
- A cobertura é de tipagem/teste, não de runtime: um nó que não herde `Expr` ainda
  funciona por tipagem estrutural até o teste falhar.
- Se o churn de nós crescer muito, o trabalho do gerador começa do zero (o desenho fica
  no histórico da #15).

### Neutras

- Nenhuma semântica, saída ou diagnóstico muda; é uma decisão de tooling/tipagem.
- A issue #15 fecha com o PR, não como *not planned*: a decisão é “manual + guard”.

## Alternativas consideradas

| Alternativa | Por que não agora |
| --- | --- |
| Gerar nodes/protocols/`accept` de um schema | Custo de schema/generator/CI e migração de 40 nós; cobre só parte dos 9–15 arquivos que um nó toca. |
| Descriptors em runtime (`make_dataclass`) | Quebra mypy strict/IDE, arrisca `frozen`/`eq` e piora debugging. |
| Trocar `Visitor` por `match`/`singledispatch` | mypy não checa exaustividade; migração grande e perde o padrão do livro. |
| Status quo (sem guard) | Deixa o `AstPrinter` fora do mypy e mantém `Variable` fora da hierarquia. |

## Como verificar

- `uv run mypy` passa com `AstPrinter` herdando os protocols.
- `uv run pytest tests/test_ast_hierarchy.py` passa.
- `make check-fast` verde.
- Revisitar quando o gatilho da decisão 5 acontecer.

## Referências

- Issue [#15](https://github.com/loxia-lang/loxia/issues/15)
- [ADR-0004](0004-identidade-dos-nos-de-ast.md), [ADR-0107](0107-adiados-e-nao-objetivos.md)
- `loxia_core/frontend/expr.py`, `loxia_core/frontend/stmt.py`,
  `loxia_core/frontend/ast_printer.py`, `tests/test_ast_hierarchy.py`
