# ADR-0001 — Registrar decisões em ADRs

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [ADR-0002](0002-tree-walk-como-oraculo.md), [`../../TODO.md`](../../TODO.md) §11

## Contexto

As decisões estavam espalhadas por `AGENTS.md`, `TODO.md` §11, `TIPOS.md` (D-1…D-18),
`IDEIAS.md` (I-1…) e mensagens de commit. O "porquê" de uma escolha se perdia: o diff
mostra o que mudou, não as alternativas descartadas nem o custo aceito. Sem registro, uma
decisão antiga parece arbitrária e é re-discutida (ou revertida) sem contexto.

## Decisão

Adotar ADRs em `docs/adr/`, com:

- um arquivo por decisão (`NNNN-slug.md`), numeração sequencial;
- template obrigatório com contexto, decisão, consequências (positivas **e** negativas),
  alternativas e critério de verificação;
- ADR aceito imutável; mudança gera novo ADR que substitui o anterior;
- índice mantido em [`README.md`](README.md);
- especificação em [`../spec/`](../spec/) atualizada no mesmo commit que implementa a
  decisão.

Discussão em aberto continua em `IDEIAS.md`/`TODO.md`; ADR só registra o que foi decidido.

## Consequências

### Positivas

- Histórico do "porquê" legível, versionado e linkável em commits/PRs.
- Onboarding mais rápido: dá para entender o desenho sem arqueologia de git.
- Força explicitar custos e alternativas antes de implementar.

### Negativas / custos

- Um passo a mais no fluxo de mudança de linguagem.
- Risco de ADR virar documentação morta se ninguém atualizar o índice/spec.

### Neutras

- ADRs antigos podem ficar obsoletos; o status (`superseded`/`deprecated`) resolve.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só `TODO.md` §11 | mistura planejamento com decisão; sem histórico de alternativas |
| Comentários no código | não cobrem decisões de sintaxe/processo; difíceis de achar |
| Wiki externa | sai do versionamento e diverge do código |

## Como verificar

- Este ADR existe e está no índice.
- Toda decisão nova de sintaxe/semântica referencia um ADR no commit.
- Revisão: se um ADR não tem consequência negativa, ele provavelmente está incompleto.
