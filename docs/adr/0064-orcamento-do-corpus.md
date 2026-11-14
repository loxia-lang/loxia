# ADR-0064 — Orçamento do corpus: teto de `PENDING` e promessa do I1

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md), [ADR-0031](0031-backend-nativo.md),
  [`../../docs/spec/garantias.md`](../../docs/spec/garantias.md)

## Contexto

O I1 só vale para o corpus anotado. Se `PENDING` crescer sem limite, o teste diferencial
pode ficar verde enquanto a maior parte dos casos não compila. Hoje temos 4 `PENDING` em
110 casos (3,6%), mas não há gate que impeça piorar.

## Decisão proposta

- `PENDING` ≤ **5%** do total de `tests/cases` (arredondado para baixo; 5% de 110 = 5).
- Todo `PENDING` tem nível (`l6`/`l7`/...), motivo curto e justificativa; `l?` é proibido.
- Um caso só entra no corpus como `PENDING` se `--check` passa e o backend recusa com 65;
  caso contrário é bug, não dívida.
- Teste de CI calcula a razão e falha acima do teto; a mensagem diz quantos remover.
- `LEVELS` é a única promessa do I1; README/`docs/spec/garantias.md` são gerados a partir
  do manifesto, não copiados à mão.
- Para features grandes, o caso pode esperar em branch/issue em vez de inflar `PENDING`.

## Alternativas

| Alternativa | Por que não |
| --- | --- |
| 10% | Permite quase 1 em 10 casos fora do I1; enfraquece a promessa. |
| Sem teto | Foi o risco levantado na revisão; status verde vira ficção. |
| Excluir casos não suportados do corpus | Esconde a lacuna e quebra a rastreabilidade. |
| Teto absoluto (ex.: 5 casos) | Não escala com o corpus; a razão é melhor. |

## Consequências

- O teto atual passa (4/110); adicionar 2 casos sem suporte já estoura.
- O gate precisa ser barato e determinístico; entra em `tests/test_backend.py` ou arquivo
  próprio, sem subprocessos.
