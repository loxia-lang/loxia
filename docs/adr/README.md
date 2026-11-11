# ADRs — Architecture Decision Records

Registro das decisões que moldam a linguagem e o compilador. Um ADR explica **por que** a
escolha foi feita, o que ela custa e o que foi descartado — coisas que o diff não conta.

## Quando criar um ADR

Crie quando a decisão:

- muda sintaxe, semântica ou comportamento observável;
- é difícil de reverter (representação de valor, modelo de tipos, backend, formato de erro);
- tem trade-offs relevantes (imutabilidade por padrão, `Int` vs `Float`, `|>` vs UFCS);
- estabelece processo/arquitetura que todo mundo precisa seguir.

**Não** crie para bug fix, refactor interno sem consequência externa ou item de TODO.

## Fluxo

1. Discuta em [`../../IDEIAS.md`](../../IDEIAS.md), [`../../TODO.md`](../../TODO.md) ou
   [`../../TIPOS.md`](../../TIPOS.md).
2. Decida, com um caso de teste que demonstre o comportamento.
3. Crie `NNNN-slug.md` a partir do [template](template.md), com status `accepted`.
4. Atualize [`../spec/`](../spec/) para refletir o que o código faz.
5. Adicione ao índice abaixo.

## Regras

- **ADR aceito é imutável.** Mudou de ideia? Crie um novo ADR e marque o antigo como
  `superseded by ADR-XXXX`.
- Numeração sequencial de 4 dígitos; nunca reutilize um número.
- Idioma: português; identificadores de código em inglês.
- Todo ADR lista consequências **negativas** ou custos. Decisão sem custo é suspeita.
- Discussão em aberto **não** é ADR — fica em `IDEIAS.md` como `em avaliação`.

## Status

| Status | Significado |
| --- | --- |
| `proposed` | em discussão; ainda pode mudar |
| `accepted` | decidido e (quando aplicável) implementado |
| `rejected` | descartado; fica registrado o porquê |
| `superseded by ADR-XXXX` | substituído por outro ADR |
| `deprecated` | ainda vale, mas não deve ser usado em código novo |

## Índice

| # | Decisão | Status | Data |
| --- | --- | --- | --- |
| [0001](0001-registrar-decisoes-em-adrs.md) | Registrar decisões em ADRs | accepted | 2026-11-11 |
| [0002](0002-tree-walk-como-oraculo.md) | Tree-walk é a especificação executável | accepted | 2026-11-11 |
| [0003](0003-diagnosticos-por-execucao.md) | Diagnósticos por execução, sem estado global | accepted | 2026-11-11 |
| [0004](0004-identidade-dos-nos-de-ast.md) | Nós de AST têm identidade | accepted | 2026-11-11 |
| [0005](0005-val-var-imutabilidade.md) | `val`/`var` e imutabilidade de bindings | accepted | 2026-11-11 |
| [0006](0006-int-float-separados.md) | `Int` (i64) e `Float` (f64) separados | accepted | 2026-11-11 |
| [0007](0007-ranges-e-iteracao.md) | Ranges e iteração com protocolo embutido | accepted | 2026-11-11 |

## Próximas decisões que pedem ADR

Quando forem fechadas, viram ADR (hoje estão em `IDEIAS.md`/`TIPOS.md`):

- campos de classe, parâmetros opcionais/default — [I-5](../../IDEIAS.md);
- divisão inteira `//` (token vs comentário) e bitwise — [`TIPOS.md`](../../TIPOS.md) `D-4`/`D-9`;
- stdlib: builtins globais vs métodos/UFCS — [I-3](../../IDEIAS.md) (a alternativa
  pipeline foi rejeitada por enquanto; ver [I-2](../../IDEIAS.md));
- contratos/DbC e erros em JSON — [I-4](../../IDEIAS.md).
