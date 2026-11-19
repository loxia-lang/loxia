# ADR-0107 — Adiados e não-objetivos: gatilhos de reabertura

- **Status:** accepted (consolidação; sem mudança de semântica)
- **Data:** 2026-11-18
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (portão),
  [ADR-0021](0021-tipos-de-funcao.md), [ADR-0029](0029-conversoes-math.md),
  [ADR-0037](0037-async-direcao.md), [ADR-0040](0040-generics-classes-desenho.md),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md), [ADR-0081](0081-constraints-generics.md)
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
o gatilho explícito e impede que o assunto volte como ideia solta.

## Decisão

A lista canônica de adiados/não-objetivos é a tabela abaixo. Cada item só volta com o
gatilho descrito **e** uma issue de decisão que responda ao portão do
[ADR-0014](0014-identidade-e-invariantes.md) — e, se mexer em sintaxe, ao
[ADR-0066](0066-orcamento-e-gate-sintatico.md).

| Item | Onde já foi decidido | Gatilho para reabrir |
| --- | --- | --- |
| Generics além do MVP: métodos genéricos, herança de `Box[Int]`, `is`/`as` reificado, type application explícita, função genérica como valor, recursão polimórfica e variance | [ADR-0040](0040-generics-classes-desenho.md) | Um programa real que função livre/composição não expresse; um ADR por item e caso diferencial. |
| Operator overloading | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 (não-objetivo) | Um programa real em que a ausência do operador seja a principal fonte de ilegibilidade, mais um ADR que pague `Self`/interfaces genéricas separadamente do açúcar. |
| Trailing closure | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 | Um caso real + desenho de parser com uma forma canônica, sem ambiguidade com bloco/mapa. |
| `match` estrutural em uniões | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 | Muitas uniões reais com cadeias longas de `is` + proposta que separe type match (tags) de structural match (testemunhas). |
| Extension methods | [ADR-0066](0066-orcamento-e-gate-sintatico.md) §4 | Um caso que não se resolva por função livre nem por método embutido, com resolução sem ambiguidade. |
| Metaclasses e `@decorators` | [ADR-0021](0021-tipos-de-funcao.md) (classe como valor), [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate) | Dor real de fábrica/introspecção que construtor-como-valor não cubra; `Class[T]` mínimo em ADR próprio. Decorators só com justificativa muito forte. |
| Math transcendentais e constantes (`log`, `exp`, `sin`, `cos`, `tan`, `pow`, `math.pi`) | [ADR-0029](0029-conversoes-math.md), [ADR-0066](0066-orcamento-e-gate-sintatico.md) | Biblioteca determinística com testes de I3, ou API explicitamente ambient fora do I1/I3. |
| Paralelismo (multithread) | [ADR-0037](0037-async-direcao.md) (async single-thread) | Async implementado + caso de uso CPU-bound + benchmark; ADR de modelo de memória antes de qualquer sintaxe. |

> **Fora desta lista:** contratos ([issue #14](https://github.com/loxia-lang/loxia/issues/14))
> foram decididos como biblioteca no [ADR-0108](0108-contratos-como-biblioteca.md), com a
> sintaxe adiada por gatilhos; `fs.open` ([#16](https://github.com/loxia-lang/loxia/issues/16))
> e o gerador de AST ([#15](https://github.com/loxia-lang/loxia/issues/15)) continuam em
> decisão; são trabalho, não adiados.

## Consequências

- O `IDEIAS.md` pode ser removido: cada item acima tem thread em
  [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas)
  para o histórico público, e o gatilho fica aqui.
- "Reabrir" não é comentar na thread: é abrir uma issue de decisão, passar pelo portão e
  fechar com ADR. A thread é o parking lot; o ADR é a decisão.
- O [`../roadmap.md`](../roadmap.md) não repete a lista; ele linka este ADR.
