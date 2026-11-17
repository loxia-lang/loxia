# ADR-0103 — Site de documentação: Starlight, staging e versão da referência

- **Status:** accepted (implementação em andamento)
- **Data:** 2026-11-17
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0091](0091-doc-comments-e-geracao-de-docs.md),
  [ADR-0102](0102-ingles-na-vitrine-e-docs-pt-br.md),
  [`../../TODO.md`](../../TODO.md) §14.2

## Contexto

A documentação já é Markdown com front matter `sources:` em `docs/spec/`, `docs/tech/`,
`docs/stdlib/` (gerado) e ADRs. O site precisa ser uma projeção dessa fonte, com busca,
navegação, dark mode e i18n, sem criar uma segunda documentação. O público é internacional:
o README e a comunidade são em inglês, mas a especificação normativa ainda é em pt-BR
([ADR-0102](0102-ingles-na-vitrine-e-docs-pt-br.md)). A referência muda entre 1.0 e 1.1 e
precisa de arquivo histórico.

Decisões anteriores: a API pública da stdlib é em inglês
([ADR-0091](0091-doc-comments-e-geracao-de-docs.md)); a documentação como site e i18n está
na §14.2; o repo é privado até o PR 9.

## Decisão

1. **Stack:** Astro Starlight no diretório `site/`, com Node 24, npm e lockfile próprio.
   Node fica isolado do runtime Python; o wheel e o comando `loxia` não dependem dele.
2. **Uma fonte:** `docs/` continua a fonte. `tools/docs_site.py` gera a árvore de conteúdo
   do Starlight em `site/src/content/docs/` (ignorada pelo git), mapeando:
   - `docs/spec/` → referência pt-BR 1.1 em `/pt/reference/*`;
   - `docs/versions/1.0/reference/` → arquivo 1.0 em `/pt/1.0/reference/*`;
   - `docs/stdlib/` → `/stdlib/*` (inglês, gerado);
   - `docs/i18n/en/` → home, why, learn, cookbook, changelog e a landing de referência;
   - `README`, `CONTRIBUTING`, `SECURITY`, ADRs, `TODO`, `IDEIAS`, `TIPOS`, `ESCOPO` e
     `docs/log.md` **não** entram no site; links de ADR apontam para o GitHub.
3. **Idiomas:** inglês é o locale raiz (`/`), pt-BR fica em `/pt/`; Starlight faz fallback
   para inglês quando uma página pt ainda não existe. A referência 1.1 é publicada em
   pt-BR em `/pt/reference/*`; `/reference` é uma landing inglesa que explica o estado da
   tradução e aponta para a referência em português. Quando a tradução inglesa existir,
   `/reference/*` passa a ser a versão EN e `/pt/reference/*` continua a PT.
4. **Versionamento:** só a **referência** é versionada. `/pt/reference/*` é 1.1 (atual) e
   `/pt/1.0/reference/*` é o arquivo 1.0, com banner e sem seletor global. Learn/why/
   cookbook/stdlib/changelog são sempre atuais. Não usamos o plugin `starlight-versions`
   (ele versiona o site inteiro e ainda está em desenvolvimento inicial).
   O snapshot 1.0 é uma **cópia congelada e commitada** de `v1.0.0` em
   `docs/versions/1.0/reference/`, com links normalizados; o build não depende do tag.
   Enquanto o release 1.1.0 não sai, os rótulos são **1.0 (stable)** e **1.1 (next)**;
   depois do PR 9, 1.1 vira current.
5. **URLs:** GitHub Pages project site, `site: https://loxia-lang.github.io`,
   `base: /loxia`. Links internos são relativos para sobreviver ao `base`; domínio custom
   fica para depois, com redirects. O deploy usa `actions/configure-pages`,
   `upload-pages-artifact` e `deploy-pages`.
6. **i18n:** páginas traduzidas ficam em `docs/i18n/<locale>/...` com
   `translated_from: <sha>`; o build nunca traduz. `tools/docs_i18n.py` reporta traduções
   defasadas e o site mostra o aviso. A UI usa as traduções do Starlight; a busca é por
   locale. Inglês original (learn/why/cookbook) não é “tradução” e não leva
   `translated_from`.
7. **Gates:** `make docs-build` = `make docs-sync` + `tools/docs_site.py` + build +
   link check; `make docs-dev`, `make docs-links`, `make docs-i18n-check`,
   `make docs-version`. O CI ganha um job `site` (build/link check) no `ci.yml` e um
   workflow `docs.yml` de deploy no `main`. O `tests/test_docs_links.py` continua sendo o
   gate da fonte; o link check cobre o HTML gerado.
8. **Fora do launch:** sem playground (WASM/servidor exige sandbox e orçamento próprios),
   sem analytics por padrão, sem versionar learn/why/cookbook e sem renderizar ADRs.
   `llms.txt`/MCP ficam para a §14.3.

## Consequências

### Positivas

- A documentação tem uma cara de produto sem duplicar a fonte: o mesmo Markdown alimenta
  GitHub e site.
- O visitante inglês entende o projeto; o leitor português continua tendo a referência
  normativa completa.
- O arquivo 1.0 é reproduzível e não depende de o tag estar no CI.
- O custo de Node fica isolado em `site/`; o runtime continua sem dependências.

### Negativas / custos

- Duas toolchains (Python + Node), dois lockfiles e Dependabot para npm.
- O snapshot 1.0 é uma cópia e envelhece; links precisam ser normalizados uma vez.
- Enquanto a referência EN não existe, o site tem uma seção portuguesa; o i18n fica
  “meio traduzido” por design, com fallback e aviso.
- O `site` job e o deploy adicionam tempo de CI; o link check pode ser ruidoso.

### Neutras

- Não muda a linguagem nem I1–I4.
- O site herda a licença do projeto (MIT OR Apache-2.0).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| MkDocs Material | Um ecossistema só, mas i18n/landing/versão via plugins e UX mais simples; perdemos a vitrine que o 14.2 pede. |
| VitePress | Bom, mas menos batteries-included que Starlight para i18n/landing. |
| `starlight-versions` no site inteiro | Versiona learn/why/cookbook e cada tradução; plugin ainda em desenvolvimento inicial. |
| Build do 1.0 direto do tag no CI | Sem cópia, mas depende do histórico e de correções de links em tempo de build. |
| pt-BR como default | Contraria a vitrine inglesa do ADR-0102 e a primeira impressão internacional. |
| Renderizar os 102 ADRs no site | Dump interno; o site linka o índice no GitHub. |

## Como verificar

- `site/` builda com `npm run build` e `make docs-build`; o conteúdo gerado está no
  `.gitignore`.
- `tests/test_docs_links.py` continua verde na fonte; `make docs-links` cobre o HTML.
- A referência 1.1 aparece em `/pt/reference/*`, a 1.0 em `/pt/1.0/reference/*`, e a
  landing `/reference` explica a tradução.
- `docs/i18n/en/...` não contém tradução automática; `translated_from` é conferido.
- O CI `site` e o workflow `docs.yml` usam ações pinadas e permissões mínimas.

## Referências

- [Starlight — i18n](https://starlight.astro.build/guides/i18n/)
- [Starlight — configuração](https://starlight.astro.build/reference/configuration/)
- [`starlight-versions`](https://github.com/HiDeoo/starlight-versions) (alternativa descartada)
- [`../../TODO.md`](../../TODO.md) §14.2
