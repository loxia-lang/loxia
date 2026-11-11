# Documentação da linguagem

Portal da documentação técnica, sintática e das decisões de design.

> **Estado:** a especificação descreve o interpretador **como ele existe hoje** (Lox da
> Parte II do livro). A linguagem planejada — `;` opcional, `fn`, pipes,
> tipagem — está em [`../TODO.md`](../TODO.md) §1/§2, [`../IDEIAS.md`](../IDEIAS.md) e
> [`../TIPOS.md`](../TIPOS.md), e **não** vale para o código atual.

## Fontes de verdade

| Pergunta | Onde |
| --- | --- |
| O que a linguagem faz hoje? | [`spec/`](spec/) — léxico, sintaxe, semântica, erros |
| Como funciona por dentro? | [`tech/arquitetura.md`](tech/arquitetura.md) |
| Por que decidimos X? | [`adr/`](adr/) — Architecture Decision Records |
| O que queremos fazer depois? | [`../TODO.md`](../TODO.md), [`../IDEIAS.md`](../IDEIAS.md) |
| Tipos e modelo numérico | [`../TIPOS.md`](../TIPOS.md) |
| Regras para agentes/devs | `AGENTS.md` (local, não versionado) e `.dsh/skills/` |

Regra de manutenção: **mudou comportamento → muda `spec/` no mesmo commit**. Decisão difícil
de reverter → novo ADR. Discussão ainda aberta → `IDEIAS.md`/`TODO.md`, não `spec/`.

## Especificação

1. [Léxico](spec/lexico.md) — arquivos, comentários, tokens, literais, palavras-chave.
2. [Sintaxe](spec/sintaxe.md) — gramática EBNF, precedência, desugaring do `for`.
3. [Semântica](spec/semantica.md) — valores, escopos, funções, classes, herança, erros.
4. [Erros](spec/erros.md) — mensagens, fases, exit codes.

## Técnica

- [Arquitetura](tech/arquitetura.md) — pipeline, módulos, visitor, environments, resolver.

## Design

- [ADRs](adr/README.md) — processo, template e índice.
  - [ADR-0001](adr/0001-registrar-decisoes-em-adrs.md) — registrar decisões em ADRs.
  - [ADR-0002](adr/0002-tree-walk-como-oraculo.md) — tree-walk é a especificação executável.
  - [ADR-0003](adr/0003-diagnosticos-por-execucao.md) — diagnósticos por execução.
  - [ADR-0004](adr/0004-identidade-dos-nos-de-ast.md) — nós de AST têm identidade.
  - [ADR-0005](adr/0005-val-var-imutabilidade.md) — `val`/`var` e imutabilidade.
- [Glossário](glossario.md)
