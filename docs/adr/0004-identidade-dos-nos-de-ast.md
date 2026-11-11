# ADR-0004 — Nós de AST têm identidade

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../tech/arquitetura.md`](../tech/arquitetura.md), §4 do `AGENTS.md` (local)

## Contexto

O resolver grava a distância de cada variável em `Interpreter.locals`, usando o **nó de
AST** como chave — exatamente como o `HashMap<Expr, Integer>` do livro. Em Java, objetos
comparam por identidade por padrão. Em Python, `@dataclass(frozen=True)` gera igualdade e
hash **estruturais**: dois nós `Variable` com o mesmo token (mesmo lexema e mesma linha)
seriam a mesma chave. Exemplo: `{ var a = 1; print a; { print a; } }` na mesma linha — os
dois `a` têm tokens iguais, mas distâncias diferentes.

## Decisão

Todos os nós de `Expr` e `Stmt` são `@dataclass(frozen=True, eq=False)`: igualdade e hash
por **identidade** (`object.__eq__`/`__hash__`). O resolver e o interpretador usam
`dict[Expr, int]` normalmente.

`Token` continua com igualdade estrutural (não é usado como chave de resolução).

## Consequências

### Positivas

- Semântica igual à do livro, sem surpresas de colisão.
- Teste de regressão cobre o caso de tokens idênticos em profundidades diferentes.
- Comparação de AST por valor continua possível via `AstPrinter` (snapshot textual).

### Negativas / custos

- `node_a == node_b` passa a significar "é o mesmo objeto"; testes não podem comparar ASTs
  estruturalmente sem serializar.
- Quem criar nós novos precisa lembrar de `eq=False` (está na receita do AGENTS §3).

### Neutras

- O dicionário `locals` mantém referências fortes aos nós (como o HashMap do livro);
  memória cresce com o programa/REPL — aceitável no tree-walk.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Chavear por `id(expr)` | `id` pode ser reutilizado se o nó for coletado; exigiria retenção manual |
| `dict` com wrapper de identidade | mais código para o mesmo efeito |
| Igualdade estrutural | bug real de colisão em tokens iguais (demonstrado em teste) |

## Como verificar

- `tests/test_resolver.py::test_identical_tokens_do_not_collide_in_locals`.
- `tests/cases/scope_identity.lox` (tudo na mesma linha).
- Revisão: todo nó novo em `expr.py`/`stmt.py` usa `eq=False`.
