---
name: lox-audit
description: Auditoria estrutural por lente — arquitetura, tipos/ABI, runtime, código morto/repetição e gates/docs — com achados ranqueados, candidatos de refactor e saída em issues.
whenToUse: No fechamento de um milestone ou quando o usuário pedir "auditoria estrutural", "revisar a arquitetura" ou "sugerir refactors". Não use por PR (isso é `lox-converge`).
---

# Auditoria estrutural

## Princípio: uma lente por rodada

"Auditar o repo inteiro" produz 300 achados e nenhuma decisão. Cada rodada escolhe **uma**
lente, mede, lê, ranqueia e sai com issues. A auditoria **diagnostica e propõe**; ela não
executa o refactor.

Cadência: fechamento de milestone ou pedido explícito. **Nunca** por PR.

## 0. Escolha a lente

| Lente | Pergunta | Sinais baratos | Custo |
|---|---|---|---|
| L1 Tipos & ABI | cada tipo existe nos 4 lugares (valor Python, `Ty`, tag/layout LLVM, struct C)? | matriz 4×N, `lower_model`, `runtime/*.h` | M |
| L2 Runtime & memória | o contrato (GC, cap 512 MiB, pilha 10k, panic, handles, orçamento) é o que o código faz? | `runtime/`, `kernel_gen.h`, `--max-heap` | M |
| L3 Arquitetura | a dependência aponta só para baixo? há regra duplicada entre tree-walk, checker e backend? | grafo de imports, `docs/tech/arquitetura.md` | S |
| L4 Morto & repetição | o que ninguém chama, o que nunca roda, o que já divergiu? | coverage ratchet, `ast`, `grep`, `PENDING` | S |
| L5 Gates, docs & decisões | os gates e a documentação ainda descrevem o produto? | `docs-fresh`, ADR × código, corpus | S |

Comece pela lente com sintoma recente (bug de divergência → L1; doc mentindo → L5; suíte
lenta → L4) ou pela que ninguém rodou há mais tempo.

## 1. Baseline

`make check` verde. Se não estiver, registre o vermelho: auditar base quebrada mede lixo.

## 2. Meça antes de opinar

Sem dependência nova; use o que já existe:

- **cobertura**: `make coverage` / `.coverage.json` — caminho nunca executado é *suspeito*,
  não morto.
- **imports**: `grep -rn '^from loxia' loxia loxia_core` — `execution` importando
  `semantics` (ou `frontend` importando `execution`) é violação de camada.
- **duplicação**: o mesmo conceito em três lugares (parser/formatter/LSP, checker/backend,
  tree-walk/runtime). Duplicação que **já divergiu** é achado; sem divergência é candidato.
- **primitivas**: `runtime/kernel_gen.h` (gerado) × `primitives.py` × chamadas no backend ×
  `std/` — primitiva sem chamador ou chamada sem primitiva.
- **corpus**: `PENDING` com motivo e nível, `LEVELS` monotônico, `garantias.md` gerado.
- **docs**: `make docs-fresh`, `sources:` com glob que não casa, ADR fora do índice.
- **dívida**: `grep -rn 'TODO\|FIXME\|noqa\|type: ignore'` + `git blame` (idade).

## 3. Leia a lente

**L1 — matriz 4×N.** Para cada valor (`Nil`, `Bool`, `Int`, `Float`, `String`, `Bytes`,
`Range`, `List`, `Map`, `Tuple`, `Class`, `Instance`, `BoundMethod`, `NativeFn`, `Closure`,
`Enum`, `Exception`, opcional):

| Python | `Ty` do checker | tag/layout do backend | struct/ABI C |
|---|---|---|---|

Perguntas: todo tipo tem tag? toda tag tem lowering e vice-versa? `Any` boxeado é coerente?
o layout do ADR-0048 é o que o código faz? onde uma cópia atravessa a fronteira? onde falta
`assert isinstance` (valor dinâmico) ou `is_number`?
Um dado concreto vale mais que a matriz inteira: "`Bytes` não tem branch de truthiness no
lowering" é achado; "a ABI poderia ser melhor" é opinião.

**L2 — runtime.** GC Boehm e hard cap; pilha de 10k/64 MiB e `R1015`; panic sites; handles
(`fs.open`) e fechamento; orçamento do kernel por grupo (ADR-0123); `proc/poll`; o que o
runtime faz e o tree-walk não (assimetria declarada?) e vice-versa.

**L3 — arquitetura.** `loxia/` (CLI/LSP/MCP/formatter/test runner) importa o quê de
`loxia_core`? alguma regra de tipo nasceu no backend (I4)? algum módulo virou órfão? a
tabela de `docs/tech/arquitetura.md` e o §3 do `AGENTS.md` batem com `ls`?

**L4 — morto/repetição.** função sem chamador; branch impossível; flag sem uso; helper
duplicado; `xfail` vencido; `PENDING` fantasma; código comentado; artefato local (`.tmp-*`)
acumulado.

**L5 — gates/docs/decisões.** ADR cuja decisão não está no código (ou o inverso); skill com
comando que não existe; doc afirmando status antigo (ex.: `loxia 1.0.0` com `__version__`
1.2.0); corpus declarado × implementado; `make grammar`/`primitives`/`docs-sync` editado à
mão.

## 4. Ranqueie

`impacto (1–5) × probabilidade (1–5)` e `custo S/M/L`. Todo achado carrega: evidência
(`arquivo:linha` ou comando + saída), o que quebra **hoje**, e o que acontece se ignorar.
Sem isso vai para **suspeitas**, fora do ranking.

## 5. Candidatos de refactor

Refactor só entra se reduzir um custo concreto: duplicação que já divergiu, camada que não
paga, ABI inconsistente, acoplamento que já causou bug, caminho que impede teste.

Formato, uma linha cada:

> **o que muda** · **o que ganha** (métrica: −N linhas, −1 fonte de verdade, −X ms) ·
> **custo** S/M/L · **risco** · **prova de comportamento igual** (testes que já cobrem +
> caso novo se faltar)

Limites:

- 1–2 por rodada. Vinte candidatos é wishlist, não auditoria.
- Refactor que muda contrato/ABI → **ADR antes**.
- "Mais bonito", "mais idiomático", "mais OO" não são custo. Não entram.
- O audit **não executa**: abre issue com `size:` e segue. A execução é feature/fix normal
  (`lox-feature`, `lox-testing`), com `make check` verde entre fatias.

## 6. Saída

1. Uma issue **"Auditoria estrutural — lente X (data)"** com a matriz/ranking e o que **não**
   foi olhado.
2. N issues acionáveis, uma por achado, com evidência e critério de aceite.
3. Nada de doc novo por rodada; decisão que sair vira ADR + `docs/decisoes.md`.
4. Check que se repetiu em 2–3 rodadas → script em `.dsh/skills/lox-audit/scripts/` (zero
   dependência). Antes disso, não crie infraestrutura.

## 7. Quando virar workflow

Rodada com 3+ frentes independentes (4 módulos × 4 lentes): use `workflow`, um subagente por
fenda e um **verificador** que tenta refutar cada achado antes do ranking. Achado de
auditoria sem verificação adversarial vira boato.

## Armadilhas

- Auditar o diff: isso é `lox-converge`.
- Consertar no meio: mistura diagnóstico com mudança e invalida o baseline.
- Refactor "sem mudar comportamento" sem teste que prove isso.
- Listar estilo (`ruff`/guia) como achado estrutural.
- Transformar o ranking em documento de 40 páginas: o produto são issues, não prosa.
