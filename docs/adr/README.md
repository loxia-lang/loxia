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
| [0008](0008-heranca-class-parens.md) | Herança com `class Dog(Animal)` e construtor `init` | accepted | 2026-11-11 |
| [0009](0009-defaults-e-campos.md) | Parâmetros default e campos declarados | accepted | 2026-11-11 |
| [0010](0010-tipagem-estatica.md) | Tipagem estática gradual com `--check` | accepted | 2026-11-11 |
| [0011](0011-fn-elif-ponto-e-virgula.md) | `fn`, `elif` e `;` opcional | accepted | 2026-11-11 |
| [0012](0012-comentarios-divisao-potencia-bits.md) | Comentários, `//`, `**` e bits | accepted | 2026-11-11 |
| [0013](0013-ternario-nil-aware-escapes.md) | Ternário, `??`, `?.` e escapes | accepted | 2026-11-11 |
| [0014](0014-identidade-e-invariantes.md) | Identidade: três invariantes e portão de admissão | accepted | 2026-11-11 |
| [0015](0015-listas-tipadas.md) | Listas tipadas `List[T]`, mutáveis e invariantes | accepted | 2026-11-11 |
| [0016](0016-api-stdlib-hibrida.md) | API da stdlib: modelo híbrido, prelúdio mínimo e builtins reservados | accepted | 2026-11-11 |
| [0017](0017-mapas-hash.md) | Mapas `Map[K, V]`, literal `{ k: v }` e chave ausente explícita | accepted | 2026-11-11 |
| [0018](0018-narrowing.md) | Narrowing de fluxo para `T?` | accepted | 2026-11-11 |
| [0019](0019-interpolacao.md) | Interpolação `"${expr}"` | accepted | 2026-11-11 |
| [0020](0020-assinaturas-explicitas.md) | Assinaturas explícitas e funções declaradas depois | accepted | 2026-11-12 |
| [0021](0021-tipos-de-funcao.md) | Tipos de função nas anotações | accepted | 2026-11-12 |
| [0022](0022-lambdas.md) | Lambdas com `fn(x) => ...` e tipagem contextual | accepted | 2026-11-12 |
| [0023](0023-soundness-do-checker.md) | Soundness do checker: retorno, campos e override | accepted | 2026-11-12 |
| [0024](0024-mutacao-monomorfica.md) | Mutação monomórfica e `var x = nil` | accepted | 2026-11-12 |
| [0025](0025-is-e-narrowing.md) | `is T` e narrowing de uniões | accepted | 2026-11-12 |
| [0026](0026-freeze-1.0.md) | Freeze da 1.0: erros, determinismo, UTF-8 e escopo | accepted | 2026-11-12 |

## Próximas decisões que pedem ADR

Quando forem fechadas, viram ADR (hoje estão em `IDEIAS.md`/`TIPOS.md`/`TODO.md` §11):

- conversões da stdlib (cast/parse e o uso de `as`) — [I-3](../../IDEIAS.md) e
  [`../../TODO.md`](../../TODO.md) §11; o modelo híbrido já foi decidido no
  [ADR-0016](0016-api-stdlib-hibrida.md);
- contratos/DbC e erros em JSON — [I-4](../../IDEIAS.md);
- decisões de linguagem ainda abertas (nome, `if` expressão, `match`, exceções, generics,
  módulos, backend, conversões, unificação mutável) — [`../../TODO.md`](../../TODO.md) §11.

O resumo das decisões **já fechadas** fica em [`../decisoes.md`](../decisoes.md); este
índice continua sendo o histórico completo.

Identidade e critério de admissão de feature **não** estão mais nessa fila: foram
decididos no [ADR-0014](0014-identidade-e-invariantes.md) (ver também
[`../spec/garantias.md`](../spec/garantias.md)).
