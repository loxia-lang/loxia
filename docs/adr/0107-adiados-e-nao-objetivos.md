# ADR-0107 — Adiados e não-objetivos: gatilhos de reabertura

- **Status:** accepted (consolidação; sem mudança de semântica; atualizado por
  [ADR-0115](0115-corpus-de-conformidade-adiado.md) e
  [ADR-0116](0116-benchmarks-publicos-adiados.md) para os artefatos de release)
- **Data:** 2026-11-18
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (portão),
  [ADR-0021](0021-tipos-de-funcao.md), [ADR-0029](0029-conversoes-math.md),
  [ADR-0037](0037-async-direcao.md), [ADR-0040](0040-generics-classes-desenho.md),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md), [ADR-0081](0081-constraints-generics.md),
  [ADR-0115](0115-corpus-de-conformidade-adiado.md),
  [ADR-0116](0116-benchmarks-publicos-adiados.md) (processo/release)
- **Implementação:** nenhuma (registro de decisão)

## Contexto

O `IDEIAS.md` funcionava como parking lot, mas misturava três coisas: propostas em
avaliação, decisões de "não agora" e backlog já aceito. Com o repositório público e a
1.1.0 lançada, a organização separou:

- **trabalho** → issues (a fila está em [`../roadmap.md`](../roadmap.md));
- **ideia crua** → Discussions › Ideas;
- **decisão tomada, inclusive "não agora"** → ADR.

Este ADR consolida os itens de linguagem/runtime que continuam **deferidos** e estavam
espalhados entre `IDEIAS.md`, o [ADR-0040](0040-generics-classes-desenho.md) e o
[ADR-0066](0066-orcamento-e-gate-sintatico.md). Ele não reabre nenhuma decisão: só torna
o gatilho explícito e impede que o assunto volte como ideia solta. Decisão adiada de
processo/release fica em ADR próprio, referenciado aqui — é o caso do corpus de
conformidade ([ADR-0115](0115-corpus-de-conformidade-adiado.md)) e dos benchmarks
públicos ([ADR-0116](0116-benchmarks-publicos-adiados.md)).

## Decisão

A lista canônica de adiados/não-objetivos é a tabela abaixo. Cada item só volta com o
gatilho descrito **e** uma issue de decisão que responda ao portão do
[ADR-0014](0014-identidade-e-invariantes.md) — e, se mexer em sintaxe, ao
[ADR-0066](0066-orcamento-e-gate-sintatico.md).

| Item | Onde já foi decidido | Gatilho para reabrir |
| --- | --- | --- |
| Generics além do MVP: métodos genéricos, herança de `Box[Int]`, `is`/`as` reificado, type application explícita, função genérica como valor, recursão polimórfica e variance | [ADR-0040](0040-generics-classes-desenho.md) | Um programa real que função livre/composição não expresse; um ADR por item e caso diferencial. |
| Constraints em classes, enums e interfaces (`class C[T: Ord]`) | [ADR-0081](0081-constraints-generics.md) (só funções), [ADR-0040](0040-generics-classes-desenho.md) | Um programa real com classe/enum genérica cujo corpo use `Ord`/`Num`/método de interface no parâmetro; um ADR que estenda o ADR-0081 com validação de `Box[T]` e plano de monomorfização; interfaces genéricas (E3012) antes. |
| Operator overloading | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 (não-objetivo) | Um programa real em que a ausência do operador seja a principal fonte de ilegibilidade, mais um ADR que pague `Self`/interfaces genéricas separadamente do açúcar. |
| Trailing closure | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 | Um caso real + desenho de parser com uma forma canônica, sem ambiguidade com bloco/mapa. |
| `match` estrutural em uniões | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 | Muitas uniões reais com cadeias longas de `is` + proposta que separe type match (tags) de structural match (testemunhas). |
| Extension methods | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 | Um caso que não se resolva por função livre nem por método embutido, com resolução sem ambiguidade. |
| Metaclasses e `@decorators` | [ADR-0021](0021-tipos-de-funcao.md) (classe como valor), [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate) | Dor real de fábrica/introspecção que construtor-como-valor não cubra; `Class[T]` mínimo em ADR próprio. Decorators só com justificativa muito forte. |
| Objeto de classe como valor de função e `Type[C]` | [ADR-0044](0044-identidade-classe.md), [ADR-0150](0150-objeto-de-classe-nao-e-valor-de-funcao.md) | Um registro/fábrica heterogênea real que não se resolva por lambda/fábrica explícita; o `Type[C]` inclusivo paga `dynctor` no descritor + regra de override de `init`, o E explícito paga thunk por classe — um ADR de decisão escolhe e traz caso diferencial. |
| Math transcendentais e constantes (`log`, `exp`, `sin`, `cos`, `tan`, `pow`, `math.pi`) | [ADR-0029](0029-conversoes-math.md), [ADR-0066](0066-orcamento-e-gate-sintatico.md) | Biblioteca determinística com testes de I3, ou API explicitamente ambient fora do I1/I3. |
| Paralelismo (multithread) | [ADR-0037](0037-async-direcao.md) (async single-thread) | Async implementado + caso de uso CPU-bound + benchmark; ADR de modelo de memória antes de qualquer sintaxe. |
| Precisão do checker: escape/alias de chamada, sumários de efeito e CFG completo | [ADR-0141](0141-soundness-de-fluxo-do-checker.md) (Decisão 1 e emenda de 2026-11-26: precisão de escrita, `this.campo` e proveniência já entregues), [ADR-0032](0032-narrowing-campos-indices.md), [#216](https://github.com/loxia-lang/loxia/issues/216) | Três programas reais batem no falso positivo da chamada (**e** o checker foi portado para Loxia, F6 do [ADR-0149](0149-motores-primarios-thir-e-congelamento.md), para a análise nascer uma vez só, no corpus de paridade). |

> **Fora desta lista:** contratos ([issue #14](https://github.com/loxia-lang/loxia/issues/14))
> foram decididos como biblioteca no [ADR-0108](0108-contratos-como-biblioteca.md), com a
> sintaxe adiada por gatilhos; `fs.open` ([#16](https://github.com/loxia-lang/loxia/issues/16))
> continua em decisão; é trabalho, não adiado. O gerador de AST
> ([#15](https://github.com/loxia-lang/loxia/issues/15)) foi decidido como manual + guard
> ([ADR-0117](0117-ast-manual-e-cobertura-de-visitantes.md)), não como codegen agora. O
> corpus de conformidade
> ([#10](https://github.com/loxia-lang/loxia/issues/10)) foi adiado por decisão própria
> ([ADR-0115](0115-corpus-de-conformidade-adiado.md)) e os benchmarks públicos
> ([#13](https://github.com/loxia-lang/loxia/issues/13)) também
> ([ADR-0116](0116-benchmarks-publicos-adiados.md)): são artefatos de release, não itens
> de linguagem/runtime.

## Consequências

- O `IDEIAS.md` pode ser removido: cada item acima tem thread em
  [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas)
  para o histórico público, e o gatilho fica aqui.
- "Reabrir" não é comentar na thread: é abrir uma issue de decisão, passar pelo portão e
  fechar com ADR. A thread é o parking lot; o ADR é a decisão.
- O [`../roadmap.md`](../roadmap.md) não repete a lista; ele linka este ADR.
