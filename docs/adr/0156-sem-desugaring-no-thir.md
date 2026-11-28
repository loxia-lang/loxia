# ADR-0156 — Sem desugaring de controle no THIR (emenda ao ADR-0149 §2 e ao ADR-0154 §4)

- **Status:** accepted
- **Data:** 2026-11-28
- **Decisores:** Cássio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) (THIR e motores),
  [ADR-0154](0154-fronteira-do-thir.md) (fronteira do THIR), [ADR-0153](0153-ir-de-controle-desenho.md)
  (IR de controle), [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  [ADR-0031](0031-backend-nativo.md) (corpus diferencial)
- **Implementação:** [`loxia_core/thir/model.py`](../../loxia_core/thir/model.py),
  [`loxia_core/semantics/thir_build.py`](../../loxia_core/semantics/thir_build.py),
  [`docs/tech/thir.md`](../tech/thir.md), [`tests/test_thir.py`](../../tests/test_thir.py)

## Contexto

O [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) §2 descreve o THIR como uma árvore
“tipada e desugarada” e lista `for-in`, `?.`/`??`, interpolação, ternário e `match` entre os
desugarings que o contrato carregaria. O [ADR-0154](0154-fronteira-do-thir.md) §4 adiou essa
fatia: a v1 preservou a forma da AST para que a migração da fronteira tivesse gate `.ll` byte a
byte, e o desugaring ficaria para uma “v2” com gate comportamental. A F2 fechou com essa forma;
a #287 abriu a F3 ([#284](https://github.com/loxia-lang/loxia/issues/284)) perguntando se o
`loxvm` — primeiro consumidor que se beneficiaria de implementar menos nós — deve pagar a v2
antes de existir.

A investigação mostrou que o conjunto de açúcar **não é uniforme**:

- `??` e `?.` não são nós: são `TLogical` com `op == QUESTION_QUESTION` e `TGet` com
  `optional=True`. Não há nó a remover.
- `?:` não tem alvo: `if` é statement; desugar exigiria um nó de if-expressão (novo) ou
  `let`-temporária com hoisting, o que anula o ganho e mexe na ordem de avaliação.
- A interpolação poderia virar `+` de `str(...)` (o builtin existe e é `stringify`), mas criaria
  dependência do nome global `str` e mataria a especialização de `lower_strings`.
- `match` não desuga com os nós existentes: não existe expressão “é a variante V” — `is` aceita
  o enum como tipo, e o payload só é acessível como binding de `match`
  ([`semantica.md`](../spec/semantica.md#enums-and-match)); testar a variante e extrair o
  payload exigiria builtin escondido ou nó novo.
- `for-in` precisaria de um valor iterador com tipo no contrato; `Ty` não tem `Iterator`, e usar
  `Any` quebra I2/I4 e força box. O protocolo de usuário usa `nil` como sentinela (“nil as an
  element is not representable”), então desugar `List[Int?]` mudaria semântica; `List`/`Map`
  ainda têm *version check* de mutação durante a iteração. E o backend especializa cada tipo
  iterável (Range/String/List/Map/tupla/Bytes/instância) em
  [`lower_range.py`](../../loxia_core/backend/lower_range.py), então o desugar transformaria o
  loop idiomático `for i in 0..n` em iterador alocado.

Ou seja: o desugaring não remove a semântica; move-a para builtins escondidos, temporárias com
`Any` e spans sintéticos, e fixa **uma** estratégia de lowering para todos os motores.

## Decisão

1. **O THIR não desuga controle.** `for-in`, `match` (e os padrões), `?:`, `??`, `?.` e
   interpolação continuam nós/campos explícitos do contrato, na forma da v1. Isso é definitivo,
   não dívida da v1.
2. **“THIR v2” significa evolução de schema** (campo obrigatório novo, remoção, quebra de forma),
   nunca um passe de desugaring. O `schema_version` só muda por isso.
3. **Desugaring é estratégia de motor, não contrato.** O `loxvm` avalia o nó; o backend
   especializa por tipo como hoje; um futuro compilador Loxia escolhe a própria estratégia. Um
   contrato que fixa a estratégia é layout disfarçado — a mesma razão da decisão 1 do ADR-0154.
4. **O produtor não sintetiza nós de desugaring.** `build_thir` continua copiando decisões do
   checker: nada de builtins escondidos (`__iter`, `__variant_is`), temporárias com `Any` ou spans
   inventados. Isso preserva I2 (nada implícito) e I4 (o checker é a fonte de tipos).
5. **O custo de superfície do segundo motor é aceito e policiado.** Todo `k` que o contrato
   declara tem implementação no motor, e `k`/`schema_version` desconhecido é diagnóstico estável
   (critério da F3), nunca crash.
6. **Reabrir exige ADR novo**, com um destes gatilhos: (a) um terceiro motor; (b) a F4 mostrar que
   o lowering por nó domina o código do compilador; (c) o dispatch de açúcar do avaliador ficar
   ingovernável. “Simetria” e “menos linhas” não são gatilho. Se o `loxvm` quiser um núcleo
   mínimo, o lugar aceito é um normalizador **interno** (sem tipos, sem mudança de contrato), não
   o THIR compartilhado.

## Consequências

### Positivas

- A F3 desbloqueia sem uma fatia de desugaring antes do primeiro caso de paridade.
- O snapshot do THIR e o gate `.ll` (269 casos) ficam como estão; nenhuma revisão em massa.
- Diagnósticos continuam no token original (`for`, `match`, `?.`), sem span sintético.
- O backend mantém o loop especializado por tipo (Range/String/List/Map/tupla/Bytes/instância).
- O oráculo (tree-walk sobre a AST) e os motores veem a mesma forma de alto nível; um bug de
  desugaring não vira semântica compartilhada e não testada depois do congelamento.

### Negativas / custos

- O `loxvm` implementa ~9 classes a mais (as mais fáceis: `TForIn`, `TMatch`/padrões,
  `TConditional`, `TInterp`); todo motor futuro paga por nó.
- A duplicação de lowering por construto entre motores permanece dívida declarada, policiada pelo
  diferencial I1, não por construção.
- O ADR-0149 e o ADR-0154 §4 ficam com o texto original; a correção vive na emenda e nos
  documentos atualizados, então quem lê o ADR antigo precisa seguir o ponteiro.

### Neutras

- O modelo não muda: `schema/thir-v1.json` e `tests/thir/manifest.json` ficam intactos.
- `--emit=thir` continua mostrando a forma do fonte, o que ajuda a revisão do snapshot.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| B — desugar `for-in` e `match` | `match` não tem teste de variante/payload como expressão; `for-in` exigiria tipo de iterador, sofre com `nil` como sentinela e deoptimiza o loop idiomático. |
| C — desugar tudo | Além dos problemas de B, exige nó de if-expressão e um `stringify` de linguagem; ganha superfície em vez de perdê-la. |
| D — normalizador dentro do `loxvm` | Válido, mas é uma camada a mais em Loxia sem reduzir trabalho; fica como opção interna se o dispatch crescer, sem tocar no contrato. |
| A agora, reabrir na F4 | A migração depois atingiria dois motores + snapshot de uma vez; o gatilho da decisão 6 permite reabrir sem pré-comprometer. |
| Tirar `for-in`/`match` da linguagem | Fora de escopo e sem relação com o custo do motor; a linguagem já os tem e a spec os define. |

## Como verificar

- `tests/test_thir.py::test_control_sugar_stays_explicit_in_the_contract` constrói um programa
  com as seis formas e exige `TForIn`, `TMatch`, `TConditional`, `TInterp`, `TLogical(??)` e
  `TGet(optional=True)` no módulo. Se alguém desugarar em silêncio, o teste falha.
- `tests/test_lowering_ll.py` mantém o `.ll` byte a byte; um desugaring mudaria os bytes e exigiria
  regenerar o manifesto — a decisão 2 só permite isso por mudança de schema.
- `tests/test_thir_docs.py` exige todo nó do modelo documentado em [`docs/tech/thir.md`](../tech/thir.md);
  a seção “O que o THIR não carrega” registra esta decisão.
- Critério para revisitar: os gatilhos da decisão 6.

## Referências

- #287 (a decisão), #284 (F3), #270 (F2)
- [ADR-0149](0149-motores-primarios-thir-e-congelamento.md), [ADR-0154](0154-fronteira-do-thir.md),
  [ADR-0153](0153-ir-de-controle-desenho.md)
- [`docs/tech/thir.md`](../tech/thir.md), [`docs/spec/semantica.md`](../spec/semantica.md#ranges-and-for-in),
  [`docs/spec/sintaxe.md`](../spec/sintaxe.md)
