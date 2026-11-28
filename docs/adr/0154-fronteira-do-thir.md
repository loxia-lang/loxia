# ADR-0154 — Fronteira do THIR: declaração, não layout (emenda ao ADR-0149 §2)

- **Status:** accepted
- **Data:** 2026-11-27
- **Decisores:** Cássio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) (THIR e motores),
  [ADR-0153](0153-ir-de-controle-desenho.md) (IR de controle), [ADR-0046](0046-closures-celulas-l4.md)
  (closures/células), [ADR-0045](0045-narrowing-representacao.md) (storage × flow),
  [ADR-0048](0048-abi-classes-l5.md) (ABI de classes), [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md)
  (memória, complementado pelo [ADR-0155](0155-troca-de-coletor.md))
- **Implementação:** [`loxia_core/thir/model.py`](../../loxia_core/thir/model.py),
  [`loxia_core/semantics/thir_build.py`](../../loxia_core/semantics/thir_build.py),
  [`docs/tech/thir.md`](../tech/thir.md), [`tests/test_thir.py`](../../tests/test_thir.py),
  [`tests/test_thir_docs.py`](../../tests/test_thir_docs.py)

## Contexto

O [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) §2 descreve o THIR como a árvore
tipada e desugarada entre o checker e os motores, e lista o que ela carrega — incluindo
“layout de classe (índices/bitmap)” e “instanciações genéricas”. Ao abrir a F2 (#270) ficou
claro que a lista, lida ao pé da letra, coloca **decisão de alvo** dentro do contrato
semântico:

- índices de campo, offsets e bitmap de `val` são layout de instância (ADR-0048), não
  significado do programa. O `loxvm` da F3 avalia árvore e não tem bitmap; carregá-lo no THIR
  obriga o motor de referência a carregar ABI de um motor que ele não é.
- monomorfização é **estratégia de codegen**. O interpretador avalia genéricos sem
  instanciar; o backend instancia para emitir código. Se o THIR já monomorfiza, a F3 herda a
  estratégia do backend.
- `depth` (distância léxica por nó) existe porque o motor caminha o encadeamento de escopos.
  Com capturas explícitas por função, o encadeamento já está resolvido e `depth` vira um
  segundo jeito de dizer a mesma coisa — exatamente a duplicação que o ADR-0149 quer matar.
- a migração do lowering precisa de um gate forte. Se a v1 do THIR também desugar
  (`match` → dispatch, `for-in` → laço), a estrutura de blocos muda junto com a fronteira e
  não existe mais “o `.ll` continua byte a byte igual”.

Nada disso muda a decisão de adoção do THIR; muda **onde fica a fronteira**.

## Decisão

1. **THIR carrega declaração, não layout.** Campos e métodos viajam com nome, ordem, tipo,
   mutabilidade, `super` e interfaces; índices, offset de palavra, bitmap e vtable são
   derivados por uma função pura de cada motor. O THIR não tem offset, slot de frame nem
   valor de LLVM.
2. **Genéricos: sites, não instâncias.** O THIR carrega `TInstance` (nome + argumentos de
   tipo) no `TCall` e no módulo; monomorfizar é decisão do backend (F2/F4) e nunca do
   contrato.
3. **Capturas explícitas, sem `depth`.** `Ref` aponta para um `DeclId` com
   `LOCAL`/`CAPTURE`/`GLOBAL`/`BUILTIN`/`UNRESOLVED` — `BUILTIN` é o nome que o checker
   pré-declara sem `Decl` no fonte (`print`, `Int`, `Result`, …), resolvido pelo nome, e
   `UNRESOLVED` fica só para o nome inexistente; a posição no `env` é o índice do `DeclId` na
   tupla `TFunction.captures`. Referências para frente de topo são resolvidas por uma
   pré-declaração que espelha a do checker, para que um programa check-limpo nunca produza
   `UNRESOLVED`. A ordem das capturas é **canônica por nome**, para que dois
   produtores independentes (o Python da F2 e o checker em Loxia da F6) cheguem ao mesmo
   snapshot. Nome repetido na mesma função é ambiguidade: o produtor falha em vez de escolher.
4. **V1 fiel, v2 desugarada.** A v1 preserva a forma da AST (`Grouping` morre; `This`/`Super`
   viram referência resolvida) e **não** introduz desugaring novo: `for-in`, `match`, `?:`,
   `??`, `?.` e interpolação continuam nós explícitos. O desugaring entra numa fatia própria,
   com gate **comportamental** (corpus/I1), porque aí a estrutura de blocos muda de propósito.
   A migração da fronteira, por sua vez, tem gate **byte a byte** no `.ll`.
5. **Nada de CFG.** Blocos, phi e cleanup continuam na IR de controle
   ([ADR-0153](0153-ir-de-controle-desenho.md)); se um construto precisar de fluxo, ele desce
   para lá.
6. **`build --emit=thir` é a superfície de debug sancionada.** A issue #270 põe “API
   pública de THIR” fora de escopo; o formato não é API de programa: é o artefato de build
   que o snapshot revisa, com `schema_version`, determinismo testado e recusa explícita. O
   nome segue o `--emit` existente (ll/obj/exe) em vez de um `--dump-thir` à parte.

## Consequências

### Positivas

- THIR neutro de motor: a F3 avalia árvore sem carregar Boehm, LLVM ou bitmap.
- A migração da F2 vira transformação mecânica e revisável, com gate de `.ll` byte a byte
  (bisect confiável) em vez de “confie no corpus”.
- Um único lugar resolve binding e captura (`thir_build` + `captures`), sem `depth` paralelo.
- Snapshot estável: ordem canônica tira ruído de travessia do diff.

### Negativas / custos

- O lowering continua derivando layout e distinguindo alvo de chamada (kernel × closure ×
  método × classe) na v1. É dívida declarada, com issue, e não contrato.
- Duas implementações de captura coexistem até a migração terminar; a equivalência é
  policiada por teste de corpus, não por construção.
- O desugaring adiado deixa `lower_enums`/`lower_range` com o código de hoje por mais tempo.
- A ordem canônica por nome pode divergir da ordem “de primeira captura” que alguém espere;
  documentado e testado.

### Neutras

- O modelo ganha `Decl.cell` (a decisão de célula deixa de ser do backend).
- `TModule` já serializa (fatia 2 da F2); o modelo nasceu sem referência de objeto.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Seguir o ADR-0149 ao pé da letra (layout e monomorfização no THIR) | Acopla a F3 a ABI de LLVM e a uma estratégia de codegen; o motor de referência passa a carregar decisão de alvo. |
| Desugar `match`/`for-in` já na v1 | Mistura “movi a fronteira” com “mudei o codegen”; perde o gate byte a byte e o bisect. |
| Manter `depth` além das capturas | Dois jeitos de dizer o mesmo binding; o segundo vira divergência silenciosa. |
| Começar por um THIR mínimo (só tipos, sem binding) | Não remove as tabelas por identidade de nó, que é o objetivo da fase. |

## Como verificar

- `tests/test_thir.py`: binding local/captura/global, célula, narrowing no nó, spans,
  `TInstance`, ids determinísticos e o corpus inteiro (capturas e contagem de células iguais
  às do `analyze_captures`).
- `tests/test_thir_docs.py`: todo nó do modelo aparece em `docs/tech/thir.md`.
- Na fatia da migração: manifesto de `sha256` do `.ll` dos casos do corpus, commitado antes
  do refactor, idêntico depois.
- Critério para revisitar: se o lowering precisar de um offset/índice que só o THIR poderia
  dar, a decisão 1 está errada e volta ao ADR; se a F3 precisar de desugaring para avaliar
  (e não só para simplificar codegen), a decisão 4 antecipa a v2.

## Referências

- [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) — a decisão de adotar o THIR.
- [ADR-0153](0153-ir-de-controle-desenho.md) — a IR que fica com o controle.
- [`docs/tech/thir.md`](../tech/thir.md) — o modelo implementado.
- [`docs/plano-de-motores.md`](../plano-de-motores.md) — fase F2.
