# ADR-0102 — Inglês na vitrine pública; docs internas em pt-BR até a tradução

- **Status:** accepted (primeira etapa implementada)
- **Data:** 2026-11-17
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0091](0091-doc-comments-e-geracao-de-docs.md),
  [ADR-0101](0101-licenca-dual-e-politica-de-contribuicao.md),
  [`../../TODO.md`](../../TODO.md) §14.2

## Contexto

O projeto sempre escreveu documentação, ADRs e comentários em português. Ao abrir o
repositório (§14.1), a vitrine precisa ser legível para quem não fala português: README,
CONTRIBUTING, SECURITY, Code of Conduct, templates, workflows e mensagens de commit. Ao
mesmo tempo, a especificação tem ~2.500 linhas, os ADRs são o registro histórico e o
roadmap é uma ferramenta de trabalho; traduzir tudo de uma vez atrasaria a abertura e
criaria duas fontes que podem divergir.

A API pública da stdlib já é documentada em inglês ([ADR-0091](0091-doc-comments-e-geracao-de-docs.md)),
e o site futuro prevê pt-BR como fonte com tradução de *learn*/*reference* (§14.2).

## Decisão

1. **Superfície pública em inglês:** `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
   `SECURITY.md`, templates de issue/PR, textos de CI, mensagens de commit, release notes e
   o `CHANGELOG` a partir da 1.1.0.
2. **Docs internas em pt-BR por enquanto:** `docs/spec/`, `docs/adr/`, `TODO.md`,
   `TIPOS.md`, `docs/roadmap.md` e `docs/tech/` continuam em português. O README e o
   `docs/README.md` declaram isso e apontam para a tradução em `TODO.md` §14.2.
3. **Código:** comentários e docstrings existentes podem ficar em pt-BR; código novo de
   API pública e mensagens de runtime são em inglês. Não há tradução em massa de
   comentários neste momento.
4. **Tradução:** quando a spec for traduzida, a versão inglesa vira a referência de
   publicação e a portuguesa pode ficar como tradução ou ser aposentada; o mecanismo de
   `sources:`/frescor continua valendo para as duas.
5. **Skill/agente:** as skills internas (`.dsh/skills/`) podem ficar em pt-BR, exceto a
   skill de commits, que é a interface usada por contribuidores e agentes.

## Consequências

### Positivas

- Um visitante internacional entende o projeto, instala, roda e contribui sem precisar de
  português.
- A tradução da spec acontece em uma etapa própria, com revisão, em vez de misturar
  tradução automática com decisões técnicas.
- O registro histórico (ADRs) não é reescrito só para trocar idioma.

### Negativas / custos

- Até a tradução, a spec e os ADRs continuam sendo uma barreira para não falantes de
  português.
- O repositório fica bilíngue por um tempo; README e CHANGELOG antigos convivem com textos
  novos em inglês.
- Toda página traduzida precisa do mesmo mecanismo de frescor, senão o inglês apodrece
  primeiro.

### Neutras

- Não muda comportamento, semântica ou I1–I4.
- A licença dual (ADR-0101) vale para os dois idiomas.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Traduzir tudo antes de abrir | Atrasa a abertura em semanas e cria uma tradução sem revisão técnica. |
| Manter tudo em pt-BR | Contradiz o objetivo de repo internacional e limita adoção. |
| Bilíngue desde o início (README.pt-BR + docs em dois idiomas) | Dobra a manutenção e ainda não resolve a spec. |
| Tradução automática sem revisão | Erros em spec de linguagem são piores que a ausência da tradução. |

## Como verificar

- `README.md` está em inglês, tem badges e a seção “Language” apontando para `TODO.md` §14.2.
- `docs/README.md` declara o estado do idioma.
- `CONTRIBUTING.md`, `SECURITY.md` e `CODE_OF_CONDUCT.md` estão em inglês.
- `tests/test_docs_links.py` cobre os arquivos de comunidade da raiz.
- A tradução da spec, quando existir, mantém `sources:` e o relatório de frescor.

## Referências

- [ADR-0091](0091-doc-comments-e-geracao-de-docs.md) — API pública em inglês
- [`../../TODO.md`](../../TODO.md) §14.2 — documentação como site e i18n
