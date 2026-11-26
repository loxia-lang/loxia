# ADR-0145 — Campo `Any` no backend: slot de duas palavras

- **Status:** accepted
- **Data:** 2026-11-25
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0079](0079-stdlib-t2.md) (campos-container; "`Any` não entra"),
  [ADR-0043](0043-layout-l5-classes.md) / [ADR-0048](0048-abi-classes-l5.md) (layout e ABI
  de classes), [ADR-0055](0055-l6-any-casts.md) (`Any` boxeado), [ADR-0144](0144-any-dinamico-exige-estreitamento.md)
  (acesso em `Any` exige estreitamento), [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md)
  (GC Boehm), [ADR-0087](0087-heap-cap-e-self-hosting.md) (self-hosting), issue
  [#196](https://github.com/loxia-lang/loxia/issues/196)
- **Implementação:** `loxia_core/backend/lower_model.py` (`FieldLayout.slot`,
  `field_words`, `ClassLayout.word_count`), `lower_class_layout.py`,
  `lower_class_codegen.py`, `lower_generics.py`, `lower_instances.py`,
  `lower_exceptions.py`, `docs/spec/semantica.md`, `tests/cases/any_field_*.lx`,
  `tests/test_backend.py`

## Contexto

O [ADR-0079](0079-stdlib-t2.md) §2 fixou o slot de campo em **uma** palavra `i64`; o box de
`Any` é `{i64 tag, i64 payload}` e não caberia, então campo `Any` era recusado com `E4001`.
A lacuna cobrava juros: `std.jsonrpc` não guarda `error.data`
([ADR-0113](0113-protocolo-stdio-jsonrpc-framing-documents.md)), `expect` não aceita `Any`
([ADR-0096](0096-testes-biblioteca-e-runner.md)) e o self-hosting precisava de enum com
payload ([ADR-0124](0124-fmt-self-host-e-pacotes-por-repo.md), [ADR-0087](0087-heap-cap-e-self-hosting.md)).

A issue #196 mostrou o pior sintoma: com inicializador, a anotação `Any` era **ignorada** e
o campo virava um slot do tipo do inicializador (`E4002` ao atribuir outro tipo). Esse
acidente foi corrigido no #196/PR #210. Agora o [ADR-0144](0144-any-dinamico-exige-estreitamento.md)
tornou o acesso seguro (membro/escrita/chamada/índice exigem `is`/`as`, e o backend honra o
narrowing), então o campo `Any` pode entrar sem virar escape dinâmico.

## Decisão

**1. Duas palavras por campo `Any`.** O struct da instância continua
`{ i8* class, i64 bitmap, i64 ... }`, mas um campo cuja representação é `Any` ocupa
**duas palavras adjacentes** `{tag, payload}`; os demais continuam com uma. A ordem é
`[tag, payload]`, a mesma de `LoxValue`, das listas boxeadas e dos locais/globais `Any`.

**2. Dois contadores independentes no layout.** `FieldLayout.index` continua sendo o ordinal
do campo (bit do bitmap, vindo de `field_count()`); `FieldLayout.slot` é o offset **absoluto**
em palavras, já contando o header (`class` + bitmap), e vem de `word_count()`. Um campo
`Any` consome duas palavras; os demais, uma. Confundir as bases (bit × palavra) é o erro
clássico desta mudança e está explícito no código.

**3. Tamanho e tipo da instância.** `ClassLayout.word_count()` soma base + palavras dos
campos; o construtor aloca `16 + 8 * word_count()` bytes e o `instance_type` é construído
com esse número nos três caminhos (classe de topo, genérica e local). Herança continua por
prefixo: as palavras da base vêm primeiro, a derivada anexa as suas.

**4. Leitura e escrita.** `_load_field`/`_store_field` ramificam por
`field.ty.ty is ValueType.ANY`: o agregado `_ANY` é carregado/gravado direto com um bitcast
para `_ANY*`, sem box por ponteiro e sem alocação por escrita. `_store_field` ainda boxeia
defensivamente se o valor não for `Any` (o `lower_exceptions` chama `_store_field` direto).
Campos sintéticos de `Exception` (`message`/`site`, String) declaram slots absolutos 2 e 3.

**5. Invariante de GC.** O slab da instância tem de continuar vindo de `lox_alloc`
(`GC_MALLOC`, varrido). O payload de um campo `Any` pode ser ponteiro (String, instância,
closure, container); como o payload está **inline** na instância varrida, ele é raiz do
coletor. Trocar a alocação da instância para `lox_alloc_atomic` tornaria o payload ponteiro
dangling sem nenhum teste quebrar de imediato — por isso a invariante fica escrita aqui.

**6. `Any?` é `Any`.** O parser normaliza `Any?` para `Any`; `nil` é uma tag, não uma
representação opcional. Nenhum código de optionais é necessário para campos `Any`.

**7. ABI.** Só classes **com** campo `Any` mudam de layout/tamanho; uma classe sem `Any`
mantém exatamente o struct e o tamanho anteriores. O descritor de classe continua com
`n_fields` **lógico** (o número de campos, não de palavras).

## Consequências

### Positivas

- Campo `Any`/união funciona nos dois motores: leitura/escrita, `is`/`as`, igualdade, `??`,
  `print`/`str`/interpolação, containers, instância, enum e função como payload, herança nos
  dois sentidos, `Box[Any]` e classe local — tudo no corpus diferencial (`L6`).
- Some a última justificativa técnica das limitações de `std.jsonrpc`/`expect`; a migração
  da stdlib foi feita na issue [#215](https://github.com/loxia-lang/loxia/issues/215)
  (`RpcFailure.data` e `Expectation` com `Any`).
- O pré-requisito de self-hosting "campo `Any`" do [ADR-0087](0087-heap-cap-e-self-hosting.md)
  sai da lista; classe recursiva continua sendo pré-requisito separado.
- Zero alocação por escrita: `+8 B` por campo `Any` na instância e dois `load`/`store` por
  acesso, em vez de um box alocado a cada atribuição.

### Negativas / custos

- O layout de instância deixa de ser homogêneo (`i64` por campo); ADR-0043/0048 ficam
  emendados. Classes com muitos campos `Any` gastam o dobro de memória nesses campos.
- O limite de 64 campos do bitmap continua; o custo passa a ser em bytes, não em slots.
- Cada acesso a campo `Any` é um par de palavras; não é hot path fora de código que já usa
  `Any`.
- Inicializador de campo continua **constante** (regra da linguagem); atribuir no `init`
  funciona. Um valor de função pode ser guardado e impresso, mas **chamar** exige
  `as fn(T) -> U`, que ainda é `E3013`; o mesmo vale para estreitar para interface ou
  objeto de classe ([#213](https://github.com/loxia-lang/loxia/issues/213)).

### Neutras

- `Any` em campo não muda a regra de acesso do [ADR-0144](0144-any-dinamico-exige-estreitamento.md):
  `c.x.m()` sem narrowing continua `E3025`; a forma correta é
  `(c.x as C).m()`/`if (c.x is C)`.
- O corpus ganha dois casos `L6` (`any_field_assign`, `any_field_layout`) e um erro de check
  (`any_field_member`).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Ponteiro para um box alocado a cada escrita | Mantém o slot `i64` e a ABI, mas cria uma terceira representação de `Any` (ponteiro para box) só em campo, com regra de `nil`/aliasing própria e uma alocação por atribuição; o ADR-0079 já usa ponteiro para containers, mas `Any` é valor e o box inline é o mesmo de lista/global/célula |
| Uma célula de 16 bytes por campo, alocada no construtor e mutada | Evita o churn de alocação, mas gasta 24 B por campo (`slot` + célula), exige inicialização de célula no ctor e adiciona indireção em toda leitura/escrita; o inline é mais simples e mais barato |
| Alargar **todos** os campos para 16 bytes | Duplicaria a memória de toda instância do corpus, inclusive classes sem `Any`; não se paga |
| Manter a recusa `E4001` | Deixa `std.jsonrpc`/`expect`/self-hosting com workaround, e a issue #196 mostrou que a recusa acidental era pior que a lacuna |

## Como verificar

- `tests/cases/any_field_assign.lx` (diferencial l6): todos os tags, união, `nil`, lista,
  `??` e igualdade.
- `tests/cases/any_field_layout.lx` (diferencial l6): campo `Any` entre dois `Int`, herança
  nos dois sentidos, `Box[Any]`, `val Any` no `init`, classe local e laço com três campos
  `Any`.
- `tests/cases/errors/any_field_member.lx`: `c.x.m()` continua `E3025`.
- `tests/cases/std_jsonrpc_data.lx` e `tests/cases/std_test_any.lx` (diferencial l6): o campo
  `Any` da stdlib nos dois motores — `RpcFailure.data` (mapa/lista/escalar/`nil`, accessor
  tipado e builder) e `expect` com valor dinâmico.
- `tests/test_backend.py::test_campo_anotado_decide_o_layout_nao_o_inicializador` (união) e
  `test_promocao_int_para_float_em_campo_e_recusada_pelos_dois` (anotação manda, sem `E4002`).
- A varredura de I4 (`test_i4_check_limpo_nunca_vira_erro_de_tipo_no_lowering`) inclui os
  novos casos e exige que a única recusa de um check limpo seja a lacuna declarada.
- Revisitar se o layout heterogêneo começar a custar em benchmark; a alternativa é
  `word_count` por classe com campos agrupados, não voltar ao slot único.

## Referências

- [ADR-0079](0079-stdlib-t2.md) — containers em campo e a recusa original de `Any`.
- [ADR-0048](0048-abi-classes-l5.md) — ABI/descritor de classes.
- [ADR-0055](0055-l6-any-casts.md) — `Any` boxeado e `is`/`as`.
- [ADR-0144](0144-any-dinamico-exige-estreitamento.md) — acesso em `Any` exige narrowing.
- [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) — Boehm varre a instância.
