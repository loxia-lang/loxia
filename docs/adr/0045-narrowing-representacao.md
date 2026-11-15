# ADR-0045 — Narrowing e tipos de representação no backend

- **Status:** accepted (checker/tree-walk/backend implementados; captura no [ADR-0086](0086-narrowing-captura-e-merge.md))
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0018](0018-narrowing.md), [ADR-0032](0032-narrowing-campos-indices.md),
  [ADR-0031](0031-backend-nativo.md), [ADR-0043](0043-layout-l5-classes.md),
  [`../../TODO.md`](../../TODO.md) §2, [`../spec/semantica.md`](../spec/semantica.md)

## Contexto

O backend L0–L3 quase não usa os tipos publicados pelo checker; no L5 isso muda: layout de
campo, representação de `T?` e escolha de operação desboxada vêm do checker. O narrowing
de fluxo, porém, é **deliberadamente incompleto**: uma chamada que muta `p.nome` não
invalida o refino ([ADR-0032](0032-narrowing-campos-indices.md)) e uma closure que muta um
`var` capturado também não ([ADR-0018](0018-narrowing.md)). Se o lowering confiar no tipo
estreitado para escolher representação, um refino errado vira miscompile — não apenas um
erro de tipo.

O ADR-0031 já fixou que o backend **não re-infere** tipos: consome o que o checker publica.
Este ADR acrescenta o que exatamente é consumido e como o checker fica conservador.

## Decisões

1. **Dois mapas, um contrato.** O checker publica:
   - `checker.types[expr]` — tipo de **fluxo** (com narrowing), para diagnóstico;
   - `checker.storage_types[expr]` — tipo de **representação** (declarado), sem narrowing.
   O lowering usa `storage_types` para layout, offsets, representação de `T?`, chamadas e
   operações desboxadas; `types` pode informar diagnóstico/testes, nunca representação.
2. **Variáveis.** `storage_types[x]` é o tipo declarado (`Int?`, `Box[Int]`, ...), mesmo
   dentro de `if (x != nil)`. O nil check continua sendo emitido a partir da representação;
   o refino não remove o check.
3. **Campos e índices.** `storage_types[p.nome]` é o tipo declarado do campo (substituindo
   genéricos), independentemente de `p` estar estreitado; idem `xs[0]`. Acesso a membro
   ainda exige objeto não nulo no fluxo (o checker já garante isso); o que não se propaga
   é o tipo do resultado.
4. **Invalidação conservadora (B).** Desde o [ADR-0086](0086-narrowing-captura-e-merge.md),
   variáveis mutáveis capturadas também são invalidadas por chamadas que podem executar
   código do usuário; chamadas nativas puras não. Qualquer:
   - chamada de função/método (inclui nativas);
   - atribuição a campo (`p.x = ...`);
   - atribuição a índice (`xs[0] = ...`, `m[k] = ...`)

   remove **todos** os refinamentos de campo/índice ativos. Refinos de variáveis locais
   continuam (o ADR-0018 já documenta a limitação de `var` capturado por closure; o item 1
   protege o codegen mesmo assim).
5. **Por que invalidação ampla.** Sem análise de aliasing, `val q = p; q.x = nil` muda
   `p.x`; qualquer chamada pode mutar qualquer objeto alcançável. Invalidar só o caminho
   atribuído não é som. A perda de precisão é aceita: depois de uma chamada, o usuário copia
   para um local ou re-testa. O ADR-0032 rejeitava invalidar em toda chamada pelo custo de
   precisão; o L5 muda o custo-benefício porque agora há codegen.
6. **CFG/aliasing completo fica fora.** A análise de fluxo com aliases e efeitos continua
   no §2 do TODO; o par (storage_types + invalidação) é o mínimo que impede miscompile e
   mantém o checker útil.

## Consequências

- Um refino errado não muda layout nem representação; no pior caso o programa é aceito no
  `--check` e falha em runtime como o interpretador (panic, não UB).
- `if (p.nome != nil) { print len(p.nome); foo(); print len(p.nome) }` perde o refino no
  segundo uso; é o preço da invalidação em chamada.
- `storage_types` é a fonte única para o L5/L6 (não há re-inferência no lowering).
- Testes novos: refino de campo não muda a representação; chamada/atribuição a campo/índice
  derruba o refino; alias via `val q = p` também.

## Alternativas rejeitadas

- **Confiar em `types` e tornar o narrowing completo:** CFG/aliasing/efeitos é grande demais
  para antes do L5.
- **Invalidar todo refino (inclusive variáveis) em qualquer chamada:** perderia
  `if (x != nil) { foo(); len(x) }` em qualquer programa com função; precisão
  desproporcional.
- **Não invalidar e documentar:** deixa a porta aberta para miscompile no L5.
- **Re-inferir no backend:** proibido pelo ADR-0031 (duas fontes de verdade).

## Como verificar

- `tests/test_checker.py`: campo/índice perde refino após chamada, `p.x = ...` e alias;
  `storage_types` de variável estreitada continua o tipo declarado.
- No L5: teste diferencial de `T?` de campo com e sem narrowing; nil check presente.
