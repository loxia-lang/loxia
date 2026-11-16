---
name: lox-docs
description: Manter docs/ em passo com o código — rodar o relatório de frescor derivado do git, triar cada página candidata (updated/no-change + motivo), registrar em docs/log.md e fechar com os gates de cobertura.
whenToUse: Depois de mexer em superfície documentada (backend, checker, CLI, manifesto do corpus, ADRs), antes de release, ou quando o `make check` acusar o gate de docs.
---

# Documentação em passo com o código

Duas coisas diferentes, e só uma é gate:

| Eixo | Mecânico? | Onde |
| --- | --- | --- |
| **Cobertura** (fato verificável) | ✅ bloqueia no `make check` | [`tests/test_docs_consistency.py`](../../../tests/test_docs_consistency.py) |
| **Frescor** (julgamento: o texto ainda é verdade?) | ❌ relatório + ledger | [`docs/_hooks/freshness.py`](../../_hooks/freshness.py) + [`docs/log.md`](../../log.md) |

Inspirado no fluxo do `documenter` do Scrinalia (ADR 0010 de lá): o frescor é **derivado do
git**, sem campo `reviewed:` que envelhece sozinho, e o que bloqueia é cobertura de fatos,
não julgamento de prosa.

## Ground rules

- **Nunca afirme o que não verificou.** Toda frase de página tem que ser rastreável a um
  arquivo, comando ou teste que você leu/rodou.
- **Não avance o frescor tocando a página.** `no-change` com motivo é resposta legítima;
  editar por editar apaga o sinal.
- **Não documente intenção.** Se não está no `loxia_core/`, pertence ao `TODO.md` §11, não à spec.
- **Números absolutos envelhecem.** Prefira "gerado do manifesto" a "1042 testes"; se um
  número aparece, ou é gerado (`docs/_hooks/levels.py`) ou tem teste que o compara.

## Workflow

1. **Rode o relatório:** `make docs-fresh` (ou `uv run python docs/_hooks/freshness.py`).
   Ele lista, por página, quantos commits tocaram as `sources:` depois da página.
2. **Leia o diff das fontes**, não o commit inteiro. A unidade é a superfície: "o ABI de
   classe mudou", não "3 commits".
3. **Decida por página:** `updated` (texto mudou) ou `no-change` (continua verdadeiro +
   por quê).
4. **Escreva** mantendo voz, títulos e estilo. Se o comportamento observável mudou,
   `docs/spec/` no **mesmo commit** — é regra do `AGENTS.md` §4.
5. **Rode os gates:** `make check` (inclui cobertura de docs + suíte) e, se mexeu em
   backend, `make bench`.
6. **Registre** em [`docs/log.md`](../../log.md): data, intervalo e uma linha por página.

## Quando o gate de cobertura falha

| Falha | Correção |
| --- | --- |
| ADR sem linha no índice | adicione a linha em `docs/adr/README.md` |
| número de ADR duplicado/lacuna | renumere o **novo** (nunca reuse número); atualize índice, `docs/decisoes.md` e referências cruzadas |
| índice aponta para arquivo errado | corrija o link; o número do título tem que casar com o nome |
| página de spec fora do README | linke em `README.md` §Documentação |
| `sources:` ausente ou glob sem arquivo | ajuste o front matter (módulo renomeado? removido?) |
| flag do CLI fora do README | documente a flag (ou remova a menção inventada) |
| bloco de níveis defasado | `make docs-sync` |
| frase defasada na lista | reescreva com o fato atual (a lista existe para não repetir erro) |

## Anti-padrões

- Atualizar `docs/log.md` sem ler o diff ("revisado em lote").
- Mudar `sources:` para apontar só para arquivos estáveis e o relatório ficar quieto.
- Corrigir a prosa e deixar o ADR velho sem nota de atualização — ADR aceito é imutável,
  mas o cabeçalho pode e deve apontar quem o atualizou (`atualizado por ADR-XXXX`).
- Duplicar o status do corpus na prosa em vez de usar o bloco gerado.
