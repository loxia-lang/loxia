# ADR-0065 — HIR-lite: escopo, gatilho e não fazer HIR completa

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0046](0046-closures-celulas-l4.md), [ADR-0050](0050-monomorfizacao-t7.md),
  [ADR-0061](0061-l6-enums-match.md), [ADR-0062](0062-l6-excecoes-unwinding.md)

## Contexto

O L6a–L6h foi feito sem HIR: containers/`Any` foram para o runtime boxeado, T7 usou
substituição de tipos, captura ficou num passe separado. A extração em módulos evitou a
HIR. O que resta — `match` e exceções — é controle, não representação de valor.

## Decisão proposta

- **Não** introduzir HIR completa nem reescrever L0–L6.
- `match` é lowering direto com um helper local de decisão/phi.
- Exceções usam a ABI do ADR-0062 e uma pilha de cleanup; não exigem HIR para começar.
- **Gatilho explícito** para HIR-lite: se `lower_exceptions.py`/`lower_enums.py` passar de
  ~350 linhas, precisar de mais de 2 níveis de blocos aninhados manuais ou duplicar
  controle do interpretador, parar e propor HIR-lite **só para controle** (blocos, phi,
  cleanup, pattern), não para tipos/valores.
- HIR-lite, se necessária, é incremental: entra pelos nós novos, mantém os caminhos
  verdes, e tem teste diferencial próprio.

## Alternativas

| Alternativa | Por que não agora |
| --- | --- |
| HIR completa antes de exceções | Custo/risco alto; o design de setjmp/cleanup pode ser validado sem ela. |
| HIR-lite imediata | Ainda não há evidência de que o helper direto não basta; pagaria antes da dor. |
| Sem HIR e sem gatilho | Repetiria o problema do L5: complexidade crescendo sem critério de parada. |

## Consequências

- A decisão do ADR-0046/0050 continua válida para o que já foi feito.
- O gatilho fica mensurável; se for atingido, o ADR-0065 é revisado para accepted com
  escopo concreto, não vira HIR geral.
