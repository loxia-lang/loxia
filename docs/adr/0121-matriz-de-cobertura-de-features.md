# ADR-0121 — Matriz de cobertura por feature da linguagem

- **Status:** accepted (implementado)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0096](0096-testes-biblioteca-e-runner.md) (`loxia test`),
  [ADR-0031](0031-backend-nativo.md) (corpus diferencial), [ADR-0064](0064-orcamento-do-corpus.md)
  (orçamento do corpus), [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  issue [#11](https://github.com/loxia-lang/loxia/issues/11)
- **Implementação:** `tests/features.toml`, `tests/features.snapshot.json`,
  `tools/feature_coverage.py`, `docs/tech/test-coverage.md`,
  `tests/test_feature_coverage.py`, `make features`

## Contexto

O repositório tem **276 goldens** em `tests/cases/` e **173 casos** no corpus
diferencial (`LEVELS`), mas nenhum mapa diz **qual feature** cada caso cobre. O
resultado é uma cobertura que parece grande e não responde à pergunta que importa:
“a feature X tem teste no tree-walk e no binário?”. O item de cobertura do #11 pedia
exatamente isso, não uma porcentagem de linhas.

Cobertura de linhas Lox (`loxia test --coverage`) e cobertura Python (`coverage.py`) são
problemas diferentes, com custo e consumidor diferentes. O primeiro exige instrumentar
os dois motores; o segundo mede a implementação, não a linguagem. Nenhum dos dois
substitui o mapa feature → caso.

## Decisão

**Uma matriz curada em `tests/features.toml`, congelada por snapshot e validada no CI,
gerando uma página derivada.**

### 1. Fonte

Cada feature tem `title`, `golden` (um ou mais `tests/cases/*.lx`), `differential`
(uma chave de `LEVELS` ou `"none"`) e `backend` (bool). A lista é curada: features de
alto nível (`values`, `operators`, `classes`, `generics`, `exceptions`, `stdlib`, …), não
cada token do scanner.

### 2. Validação (`tools/feature_coverage.py`)

- todo golden existe e está em `tests/cases/`;
- `differential` é um nível real, e pelo menos um golden da feature está naquele nível;
- `backend = false` exige `differential = "none"`; `backend = true` exige um nível;
- **todo nível de `LEVELS`** é coberto por pelo menos uma feature (pega nível órfão);
- a matriz não pode ficar vazia.

### 3. Snapshot

`tests/features.snapshot.json` congela `{id: {differential, golden}}`. Mudar a matriz
(caso novo, nível, remoção) exige atualizar o snapshot de forma explícita
(`make features`), então uma feature não some em silêncio. O snapshot não é um golden de
saída: é a lista congelada de cobertura.

### 4. Documento derivado

`docs/tech/test-coverage.md` é gerado com a tabela e os totais; `--check` falha se a
página ou o snapshot estiverem defasados. O documento é linkado no README e o gate roda
em `tests/test_feature_coverage.py`.

### 5. O que fica de fora

- Cobertura de linhas **Lox** (instrumentar interpreter + backend) — issue própria, só
  com consumidor real.
- Cobertura **Python** (`coverage.py`) — pode ser adicionada como medição/ratchet da
  implementação, sem se chamar “cobertura da linguagem”.
- Snapshot de AST/stdout — o ADR-0121 cobre a matriz, não um novo formato de snapshot.

## Consequências

### Positivas

- A pergunta “feature X tem caso tree-walk e backend?” passa a ter resposta mecânica.
- Níveis órfãos e features sem caso aparecem no CI, não em revisão manual.
- O custo é um TOML curado e um gerador; não toca no runtime nem no corpus.

### Negativas / custos

- A lista é curada: uma feature nova não entra sozinha; alguém precisa mapeá-la.
- O snapshot gera atrito intencional a cada mudança de matriz.
- A matriz não prova qualidade do caso (um golden fraco conta igual); é um mapa de
  existência, não de profundidade.
- Features `backend = false` podem esconder uma lacuna se o nível for atualizado sem
  revisar a matriz; o `--check` pega nível órfão, não intenção.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Gerar features dos `TokenType`/nós de AST | Granularidade de implementação; não responde “classe tem teste?” e gera centenas de entradas. |
| Cobertura de linhas Lox agora | Exige instrumentar os dois motores; não era o pedido do #11 e não tem consumidor. |
| Só `coverage.py` | Mede Python, não a linguagem; não mostra lacuna de backend. |
| Sem snapshot | A matriz mudaria sem revisão e features sumiriam em silêncio. |
| Doc gerado de `git grep` | Heurística frágil; o mapeamento é uma decisão, não um grep. |

## Como verificar

- `uv run pytest tests/test_feature_coverage.py` — validação, snapshot e doc.
- `make features` — regenera snapshot/doc; `--check` no CI.
- `make check-fast` verde.

**Critério para revisitar:** a matriz passar de ~60 features, ou a necessidade de mapear
caso a caso (não só por feature/nível); aí um formato mais próximo do manifesto do corpus
entra.
