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
| [0027](0027-generics-t3b.md) | Generics T3b: funções, monomorfização e inferência | accepted | 2026-11-12 |
| [0028](0028-overflow-debug.md) | Overflow checado no modo `--debug` | accepted | 2026-11-12 |
| [0029](0029-conversoes-math.md) | Conversões (`as`, parse) e `math.*` determinístico | accepted | 2026-11-12 |
| [0030](0030-tuplas.md) | Tuplas: sintaxe escolhida, implementação pós-1.0 | accepted (pós-1.0) | 2026-11-12 |
| [0031](0031-backend-nativo.md) | Backend nativo: contrato de valor, runtime e corpus | accepted (L0–L4; L5–L7 pendentes) | 2026-11-12 |
| [0032](0032-narrowing-campos-indices.md) | Narrowing de campos e índices literais | accepted | 2026-11-12 |
| [0033](0033-inferencia-t3c-t4.md) | Inferência T3c/T4 | accepted (T4; T3c revertido no ADR-0034) | 2026-11-12 |
| [0034](0034-t3c-revertido.md) | T3c revertido: parâmetro implícito sai | accepted | 2026-11-12 |
| [0035](0035-strings-texto.md) | Strings como texto: code points e ordem | accepted | 2026-11-12 |
| [0036](0036-tuplas-implementacao.md) | Tuplas: implementação no interpretador e checker | accepted | 2026-11-12 |
| [0037](0037-async-direcao.md) | Async: colored, determinístico e pós-M7 | accepted (direção; keywords reservadas) | 2026-11-12 |
| [0038](0038-traits-nominais.md) | Traits nominais e métodos default | accepted (pós-MVP) | 2026-11-12 |
| [0039](0039-decisoes-tipos-pendentes.md) | Decisões de tipos pendentes | accepted | 2026-11-12 |
| [0040](0040-generics-classes-desenho.md) | Classes genéricas (T6a): desenho | accepted (MVP; follow-ups adiados) | 2026-11-12 |
| [0041](0041-enums-match.md) | Enums genéricos, `match` exaustivo e `Result` | accepted (MVP; backend L6) | 2026-11-13 |
| [0042](0042-excecoes.md) | Exceções: `try`/`except`/`finally`/`raise` | accepted (tree-walk; backend L6) | 2026-11-13 |
| [0043](0043-layout-l5-classes.md) | Layout L5: classes, campos, vtable e `init` | accepted (desenho; backend L5 pendente) | 2026-11-13 |
| [0044](0044-identidade-classe.md) | Identidade de classe em runtime (`is`/`as`/`except`) | accepted (tree-walk; backend L5 pendente) | 2026-11-13 |
| [0045](0045-narrowing-representacao.md) | Narrowing e tipos de representação | accepted (checker/tree-walk; backend L5 pendente) | 2026-11-13 |
| [0046](0046-closures-celulas-l4.md) | L4: closures, células e valores de função | accepted (backend L4 implementado) | 2026-11-13 |
| [0047](0047-optionais-escalares-l2-5.md) | L2.5: optionais escalares, `nil` contextual e unwrap seguro | accepted (backend L2.5 implementado) | 2026-11-13 |
| [0048](0048-abi-classes-l5.md) | L5: ABI de métodos, descritor de classe e instância | accepted (L5a/L5b/L5c implementados) | 2026-11-13 |
| [0049](0049-any-boxeado-spike-l6.md) | L6: `Any` boxeado como spike de união | accepted (spike; não é `Any` completo) | 2026-11-13 |
| [0050](0050-monomorfizacao-t7.md) | T7: monomorfização de funções e classes genéricas | accepted (T7a/b/c; containers no L6) | 2026-11-13 |
| [0051](0051-l6-range-for-in-escalares.md) | L6a: Range, `for-in` e operações escalares | accepted (containers/tuplas/Any/enums/exceções pendentes) | 2026-11-13 |
| [0052](0052-l6-listas.md) | L6b: listas boxeadas no runtime | accepted (Map/tuplas/Any/enums/exceções pendentes) | 2026-11-13 |
| [0053](0053-l6-mapas.md) | L6c: mapas boxeados no runtime | accepted (tuplas/Any/enums/exceções pendentes) | 2026-11-13 |
| [0054](0054-l6-tuplas.md) | L6d: tuplas boxeadas | accepted (Any/is/as/for-in de tupla pendentes) | 2026-11-13 |
| [0055](0055-l6-any-casts.md) | L6e: `Any` com unbox, `is`/`as`, igualdade e tuple `for-in` | accepted (primeira fatia) | 2026-11-13 |
| [0056](0056-l6-math-parse.md) | L6f: `math.*` e `Int.parse`/`Float.parse` | accepted | 2026-11-13 |
| [0057](0057-l6-defaults-as-value.md) | L6g: função com defaults como valor | accepted | 2026-11-13 |
| [0058](0058-l6-loop-capture-uninit.md) | L6h: captura por iteração, variável nil e índice de tupla `Any` | accepted | 2026-11-13 |
| [0059](0059-i4-check-limpo-compila.md) | I4: check limpo compila; promoção só na aritmética | accepted | 2026-11-13 |
| [0060](0060-orcamento-de-memoria.md) | Orçamento de memória (arena de 64 MiB) no contrato | superseded by [0074](0074-gc-boehm-e-contrato-de-memoria.md) | 2026-11-13 |
| [0061](0061-l6-enums-match.md) | L6i: enums, `Result` e `match` | accepted | 2026-11-13 |
| [0062](0062-l6-excecoes-unwinding.md) | L6j: exceções, ABI de unwinding e cleanup | accepted | 2026-11-13 |
| [0063](0063-orcamento-monomorfizacao.md) | Orçamento de monomorfização e valor genérico | accepted | 2026-11-13 |
| [0064](0064-orcamento-do-corpus.md) | Teto de 5% para `PENDING` e promessa do I1 | accepted | 2026-11-13 |
| [0065](0065-hir-lite-controle.md) | HIR-lite: escopo, gatilho e não fazer HIR completa | accepted | 2026-11-13 |
| [0066](0066-orcamento-e-gate-sintatico.md) | Orçamento e gate sintático: tetos, não-objetivos e aprovação humana | accepted | 2026-11-13 |
| [0067](0067-desambiguacao-sintatica.md) | Desambiguação: `//`, brackets, `fn` em método, união em `is`, mapa | accepted | 2026-11-13 |
| [0068](0068-not-substitui-bang.md) | `not` substitui `!` como negação (uma grafia, precede igual) | accepted | 2026-11-13 |
| [0069](0069-destructuring-aninhado.md) | Destructuring aninhado recursivo em `val`/`var` | accepted | 2026-11-13 |
| [0070](0070-strings-multilinha-e-raw.md) | `"""` canônico para multilinha e raw `r"..."`/`r"""..."""` | accepted | 2026-11-13 |
| [0071](0071-primitivas-de-runtime.md) | Primitivas de runtime: fronteira nativa, tabela única e complexidade linear | accepted (plano; implementação pendente) | 2026-11-14 |
| [0072](0072-stdlib-batteries.md) | Stdlib: kernel nativo, biblioteca em Lox e política de batteries | accepted (plano; implementação pendente) | 2026-11-14 |
| [0073](0073-imports-modulos.md) | Imports, módulos-arquivo, `_` privado e desugar | accepted (implementado) | 2026-11-14 |
| [0074](0074-gc-boehm-e-contrato-de-memoria.md) | GC Boehm e contrato de memória (hard cap de 128 MiB) | accepted (implementado) | 2026-11-14 |
| [0075](0075-diagnosticos-estruturados.md) | Diagnósticos estruturados: modelo, códigos estáveis, `human`/`short`/`json` e determinismo | accepted (implementado) | 2026-11-14 |
| [0076](0076-std-lists-sort.md) | `std.lists.sort`: comparador de três vias, estável, lista nova | accepted (implementado) | 2026-11-14 |
| [0077](0077-limite-de-pilha.md) | Limite de profundidade de chamadas (1.000) e `Stack overflow.` | proposed | 2026-11-15 |


## Próximas decisões que pedem ADR

Quando forem fechadas, viram ADR (hoje estão em `IDEIAS.md`/`TIPOS.md`/`TODO.md` §11):

- contratos/DbC e erros em JSON — [I-4](../../IDEIAS.md);
- decisões de linguagem ainda abertas (nome, `if` expressão, exceções recuperáveis,
  generics de classes/métodos e constraints, backend, unificação mutável) —
  [`../../TODO.md`](../../TODO.md) §11. Tuplas foram implementadas no interpretador/checker
  ([ADR-0036](0036-tuplas-implementacao.md)); no backend ficam para o L6. Async tem
  direção decidida, mas implementação pendente ([ADR-0037](0037-async-direcao.md)).
- imports: [ADR-0073](0073-imports-modulos.md) implementado
  sintático do [ADR-0066](0066-orcamento-e-gate-sintatico.md).

O resumo das decisões **já fechadas** fica em [`../decisoes.md`](../decisoes.md); este
índice continua sendo o histórico completo.

Identidade e critério de admissão de feature **não** estão mais nessa fila: foram
decididos no [ADR-0014](0014-identidade-e-invariantes.md) (ver também
[`../spec/garantias.md`](../spec/garantias.md)).
