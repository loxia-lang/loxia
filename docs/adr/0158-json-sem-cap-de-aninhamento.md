# ADR-0158 — Leitor JSON sem cap de aninhamento (emenda ao ADR-0079)

- **Status:** accepted
- **Data:** 2026-11-28
- **Decisores:** Cássio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0079](0079-stdlib-t2.md) (stdlib T2), [ADR-0077](0077-limite-de-pilha.md)
  (limite de pilha), [ADR-0087](0087-heap-cap-e-self-hosting.md) (heap),
  [ADR-0113](0113-protocolo-stdio-jsonrpc-framing-documents.md) (`parseResult`),
  [ADR-0157](0157-invocacao-e-distribuicao-do-thir-eval.md) (payload do THIR eval)
- **Implementação:** [`std/json.lx`](../../std/json.lx),
  [`tests/cases/std_json.lx`](../../tests/cases/std_json.lx),
  [`docs/stdlib/json.md`](../stdlib/json.md) (gerado)

## Contexto

O [ADR-0079](0079-stdlib-t2.md) fixou a superfície da T2 com `std.json` determinístico,
`parse`/`stringify`/`pretty` e **profundidade 16**. O cap nasceu como proxy de segurança de
pilha: o parser era recursivo e um documento profundo consumiria frames de chamada. Só que
16 é muito mais restritivo do que o contrato que já existe — o limite de **10.000 chamadas**
do [ADR-0077](0077-limite-de-pilha.md) — e transforma JSON válido em entrada inválida por um
número mágico.

A F3 tornou o problema concreto: o payload do THIR que o avaliador precisa ler chega a **32
níveis** em 56 dos 269 casos do corpus (medido em `canonical`), e o [ADR-0157](0157-invocacao-e-distribuicao-do-thir-eval.md)
decidiu que o leitor do payload é o `std.json`, não um parser paralelo.

## Decisão

1. **`parse`/`parseResult` aceitam qualquer aninhamento que caiba na memória.** O parser usa
   uma **pilha explícita** (iterativo), não recursão de chamadas Loxia; não há cap fixo. O
   limite deixa de ser um número escolhido e passa a ser o heap ([ADR-0087](0087-heap-cap-e-self-hosting.md)).
2. **Os escritores continuam recursivos.** `stringify`/`pretty` são limitados pelo contrato de
   profundidade de chamadas (10.000, `R1015`/`Stack overflow.`), igual nos dois motores. A
   assimetria leitor/escritor é **documentada**: um valor profundo demais para o escritor
   falha com o erro de pilha padrão, não com um erro específico de JSON. Gatilho para
   reabrir: se um programa real precisar de escrita além do limite de chamadas, um ADR novo
   torna os escritores iterativos.
3. **O erro `Invalid JSON: nesting is too deep.` desaparece.** O resto do contrato fica:
   `parse` devolve `nil` e `parseResult` devolve `Err` para entrada malformada; ordem de
   inserção preservada; `Int`/`Float` distintos; chave repetida fica com o último valor;
   não-finito é rejeitado; nenhuma mensagem contém caminho, timestamp ou endereço.
4. **Memória é o backstop.** O parser aloca proporcional à entrada; um documento gigante pode
   chegar a `Out of memory.` (exit 70, ADR-0087), que é a falha declarada — nunca crash.
5. **Determinismo inalterado.** Mesma entrada ⇒ mesmos valores e mesma ordem (I3); o parser
   iterativo não introduz `set`/`dict` derivado nem ordem dependente de hash.

## Consequências

### Positivas

- O payload do THIR v1 passa a ser legível pelo `std.json` em 100% do corpus (máx. 32 níveis).
- JSON válido deixa de ser recusado por um limite arbitrário; o contrato de segurança passa a
  ser o que já é contrato (heap e pilha).
- O parser iterativo não consome a pilha de chamadas, o que importa para o THIR eval rodando
  dentro do avaliador.
- Um parser só: `std.json` continua sendo o leitor de JSON da linguagem, sem um segundo
  parser que divirja.

### Negativas / custos

- Reescreve o parser (arrays/objetos/erros), com risco de regressão em escapes, surrogates,
  números e mensagens; o golden `std_json.lx` e o corpus cobrem o caminho.
- `parse` e `stringify` deixam de ter o mesmo alcance: um valor pode ser lido e não escrito.
  Documentado e testado, mas é uma aresta.
- A mudança é **observável e quebrada**: um documento de 17 níveis que antes era `nil` agora
  é valor; entra em "Mudado (quebra)" no CHANGELOG e o ADR-0079 fica com nota de emenda.

### Neutras

- A API pública não muda (`parse`, `parseResult`, `JsonResult`); só o alcance.
- As docs de `docs/stdlib/json.md` são geradas dos doc comments; a atualização é regenerada.
- Nenhuma sintaxe, keyword ou primitiva nova.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Subir o cap para 64/128 | Continua arbitrário; o próximo payload/nível volta a bater e a decisão reabre. |
| Manter o cap e achatar o payload (THIR v2) | Mudança de serialização/artefato de revisão (269 snapshots) para resolver um limite que não deveria existir. |
| Leitor dedicado do THIR no avaliador | Dois parsers de JSON para manter e divergir; o `std.json` é a capacidade da linguagem. |
| Tornar `stringify`/`pretty` iterativos agora | Mais código (ciclo, ordem) sem dor demonstrada; fica como gatilho declarado. |
| Recusar JSON profundo e documentar | É o comportamento atual; foi exatamente o que a F3 mostrou que não serve. |

## Como verificar

- `tests/cases/std_json.lx`: 16 níveis continua parseando; 17 e 256 níveis agora parseiam e
  fazem round-trip com `stringify`; as mensagens de entrada malformada continuam iguais.
- `make test-backend`/diferencial: o golden roda nos dois motores com os mesmos bytes.
- `make stdlib-docs`/`make docs-sync`: `docs/stdlib/json.md` sem o cap.
- Critério para revisitar: o gatilho da decisão 2 (escritores) ou um documento que estoure o
  heap de forma inesperada.

## Referências

- #288 (payload do THIR eval), #284 (F3)
- [ADR-0079](0079-stdlib-t2.md), [ADR-0077](0077-limite-de-pilha.md),
  [ADR-0087](0087-heap-cap-e-self-hosting.md), [ADR-0157](0157-invocacao-e-distribuicao-do-thir-eval.md)
- [`std/json.lx`](../../std/json.lx), [`docs/stdlib/json.md`](../stdlib/json.md)
