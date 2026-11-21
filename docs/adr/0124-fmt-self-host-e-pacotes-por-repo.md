# ADR-0124 — Front-end e `loxia fmt` em Lox: escopo, oráculo e pacotes por repositório

- **Status:** proposed
- **Data:** 2026-11-20
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0092](0092-estilo-e-formatter.md) (formatter e fase Lox),
  [ADR-0114](0114-ast-recuperada-para-tooling.md) (AST e CLI estrito),
  [ADR-0100](0100-dependencias-path.md) / [ADR-0104](0104-lock-e-frozen.md) /
  [ADR-0105](0105-dependencias-git.md) (deps, lock e git),
  [ADR-0106](0106-scaffolding-new-init.md) (scaffold), [ADR-0118](0118-toml-na-toolchain-e-edicao-de-manifest.md)
  (TOML), [ADR-0122](0122-contrato-de-data-e-instante.md),
  [ADR-0123](0123-orcamento-do-kernel-por-grupo.md),
  [Discussion #32](https://github.com/loxia-lang/loxia/discussions/32) (registry),
  [`docs/roadmap.md`](../roadmap.md) (Later: self-hosting do fmt)
- **Implementação:** `tools/loxfmt/` (novo), `static/`, `tests/cases/` e `examples/` como
  corpus de paridade, `loxia/docgen.py`, CI com `--frozen`/`--offline`

## Contexto

O roadmap coloca o self-hosting na fase Later e manda **começar pelo formatador**
([`docs/roadmap.md`](../roadmap.md)). O [ADR-0092](0092-estilo-e-formatter.md) já registrou o
desenho: o `loxia fmt` Python é a referência e o dogfood em Lox vem depois, produzindo
**bytes idênticos**; e anotou o custo real — o formatter Lox **depende do parser
self-hosted**, "o exercício maior".

Isso muda o que "self-host do fmt" significa. O `loxia/formatter.py` tem ~200 linhas, mas
não é um formatador de texto: ele roda o `Scanner` e o `Parser` do núcleo e usa a AST para
decidir a estrutura ([`loxia/formatter.py`](../../loxia/formatter.py)). Portar o fmt para Lox
é, antes de tudo, **escrever scanner + parser + AST em Lox** — o formatador é o primeiro
consumidor, não o trabalho principal.

Hoje não existe parser em Lox. O que existe é o oráculo: `loxia ast`/`--dump-ast` e o
`format_source` do Python ([ADR-0114](0114-ast-recuperada-para-tooling.md)), além do corpus
(`std/`, `tests/cases/`, `examples/`).

Ao mesmo tempo, a stdlib precisa de um **consumidor real** — hoje só `examples/sales.lx`
usa T2 — e a organização quer separar pacotes por repositório. O transporte já existe:
`git` com `rev` pinada, `loxia.lock` com commit + `sha256` da árvore, cache offline e
`loxia add --git` ([ADR-0105](0105-dependencias-git.md)). Não existe registry
([#32](https://github.com/loxia-lang/loxia/discussions/32)).

O risco de sequência é conhecido: módulo que nasce em `std.*` e depois vira pacote muda o
`import` e quebra programa, porque a stdlib congela por release
([ADR-0072 §8](0072-stdlib-batteries.md); `std` é nome reservado,
[ADR-0088](0088-distribuicao-e-raizes-de-modulo.md)).

## Decisão

### 1. O programa self-hosted é o front-end em Lox; o fmt é o primeiro consumidor

Escopo dividido em quatro fases, cada uma com oráculo e critério de paridade:

| Fase | Entrega | Oráculo | Kernel |
| --- | --- | --- | --- |
| **A** | scanner + tokens + AST mínimo + parser de statements/expressões em Lox | `loxia ast` (S-expression/`--json`) sobre o corpus: árvore idêntica | **nenhum** |
| **B** | formatter em Lox sobre essa AST, arquivo único | `format_source` do Python: bytes idênticos em `std/`, `tests/cases/`, `examples/` | **nenhum** |
| **C** | driver de árvore: descobrir, pular inalterado, escrever atômico, diff no `--check` | `loxia fmt --check` + inspeção de mtime/diff | `fs.stat`, `fs.rename` (ADR-0123) + `glob`/`diff` |
| **D** | flip: `--engine=py|lox` e depois default | suíte completa + bench | — |

A fase A **não** depende de capacidade de host: é Lox puro sobre `std.strings`, `std.utf8`,
`std.lists` e `std.results`. Ela pode começar antes de qualquer decisão de kernel.

### 2. O oráculo é o Python, não a memória de quem porta

- Parser: a árvore em Lox tem que ser **igual** à do `loxia ast` no corpus; divergência é bug
  do Lox, não "diferença de estilo".
- Formatter: saída **byte a byte** igual à do Python, incluindo `;` opcional, indentação de
  2 espaços, comentários e strings multilinha.
- `--check` preserva o contrato de exit code (1 = mudaria, 0 = já formatado) e idempotência.
- A paridade roda em CI sobre o corpus inteiro, não em três arquivos de exemplo.

### 3. Fronteira: ferramenta é pacote, não `std`

| O que | Onde nasce | Por quê |
| --- | --- | --- |
| scanner/parser/AST, formatter, driver | `tools/loxfmt/` (repo principal) e, depois, `loxia-lang/fmt` | é ferramenta da linguagem; não é biblioteca de programa comum |
| `glob`, `diff`, `term`, `uri`, `semver`, `toml` | **repositório próprio desde o dia 1** | envelhecem rápido, não são pré-requisito de programa comum, e extrair depois quebra `import` |
| `timex` v2, wrappers de `fs` | `std` (ADR-0122/0123) | já são contrato bundled e têm consumidor amplo |
| `fs` mutação, `sha256` | kernel (ADR-0123) | SO/representação ou custo que Lox não paga |

Pacote que nascer em `std.*` e depois sair é quebra de import; por isso a decisão é **antes**
de adicionar. `std` continua com o que é adjacente à linguagem e usado por quase todo
programa.

### 4. Piloto de pacote: `glob`, na fase C

`glob` (match `*`/`**` + expansão) é o primeiro pacote extraído, porque:

- é pequeno, puro e testável por tabela;
- tem consumidor imediato (descoberta de arquivos do fmt na fase C);
- exercita o fluxo inteiro sem registry: scaffold → tag `v0.1.0` → `loxia add --git … --rev
  v0.1.0 --lock` → `--frozen`/`--offline` → docs.

Regra de extração: **dois consumidores** (ou o tool saindo do repo principal), nunca por
simetria. Até lá, o código vive em `tools/loxfmt/lib/` e é movido com o import ajustado no
mesmo PR.

### 5. Onde a ferramenta mora

`tools/loxfmt/` no repo principal, com `loxia.toml` próprio (nome, versão, deps) para o CI
rodar o oráculo e o teste de paridade. A extração para `loxia-lang/fmt` é decisão da fase D,
quando o comando shipped passar a ser o Lox — e aí entra o bootstrap (o `loxia` Python
executando um programa Lox embarcado, já possível pelo interpretador).

### 6. Contrato de pacote (sem registry)

- **Um repo = um pacote.** `git` dep aponta para a raiz; submódulo/monorepo de pacotes não é
  suportado pelo loader.
- `loxia.toml` com `[package] name` e `version` (X.Y.Z já validado pelo toolchain); módulos
  na raiz; `_` é privado; `loxia.lock` commitado; tag `vX.Y.Z`.
- `import <nome>` — namespace plano; `std` é reservado. Nome do pacote é o nome do import,
  então renomear repo é quebra.
- Docs geradas por `loxia doc` no próprio repo; CI com `--frozen` e cache offline.
- Descoberta sem registry: repo índice `loxia-lang/packages` (README/tabela).
- Lacunas a fechar: `loxia new --lib` (hoje o scaffold é só de aplicação), template de CI e
  cache de `.loxia/cache` no CI.

### 7. Não-objetivos desta rodada

Registry e resolução de versões ([#32](https://github.com/loxia-lang/loxia/discussions/32)),
ranges de semver (não há resolver; `semver` em Lox fica em parse/compare/bump), TLS/rede
([#31](https://github.com/loxia-lang/loxia/discussions/31)), LSP em Lox e features de
formatter além da paridade (arquivo de config, lint, reflow).

## Consequências

### Positivas

- O consumidor real passa a existir e dirige a stdlib: cada módulo nasce com uso, não com
  simetria.
- O oráculo já está pronto (`loxia ast` + `format_source`), então a paridade é mensurável em
  CI desde a fase A.
- `std` evita a promessa de cinco anos para ferramenta de nicho; o fluxo de pacote é provado
  sem registry.
- O parser em Lox é o melhor dogfood possível: expõe lacunas de tipos, tuplas, enums e erros
  com dor real.

### Negativas / custos

- A fase A é **XL**: scanner + parser + AST em Lox, com precedência, `;` opcional, `fn`
  opcional, interpolação e recuperação de erro. É maior que o formatter.
- Duas implementações até a paridade; divergência silenciosa é o risco, mitigado pelo
  diferencial de AST e de bytes em CI.
- Formatter em Lox será mais lento que Python; sem bench, a regressão passa despercebida.
- Dependência `git` no desenvolvimento do repo principal exige cache/`--offline` no CI.
- Multi-repo multiplica CI, docs e releases; sem registry, a descoberta é manual.
- Escopo escorrega fácil para "formatador completo" e para "LSP em Lox"; o ADR fixa a
  paridade como teto.

### Neutras

- `tools/loxfmt` é um projeto dentro do repo, com manifest próprio; não muda o build da
  linguagem.
- `loxia fmt` continua Python até a fase D; o default não muda por este ADR.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter o fmt em Python e crescer a stdlib por simetria | Sem consumidor real, cada módulo é dívida paga pelo codegen; o roadmap já aponta o fmt como começo. |
| Colocar `glob`/`diff`/`term` em `std` agora | Extrair depois muda o `import` e quebra programa; `std` congela por release. |
| Esperar o registry ([#32](https://github.com/loxia-lang/loxia/discussions/32)) | Bloqueia tudo; `git` + lock já resolve transporte, pin e offline. |
| Monorepo de pacotes | `git` dep aponta para a raiz do repo; subdiretório não é suportado pelo loader. |
| Formatter nativo em Python, mais rápido | Não dogfooda a linguagem e não cria consumidor para a stdlib. |
| Começar pelo driver de árvore (glob/fs) antes do parser | Inverte o custo: o driver é a parte fácil e não valida nada da linguagem. |

## Como verificar

- **AST**: para cada arquivo do corpus, `loxia ast` (S-expression/JSON) × árvore do parser
  em Lox — igualdade estrutural; caso negativo com erro de sintaxe (posição e mensagem).
- **Formatter**: bytes idênticos ao Python em `std/`, `tests/cases/` e `examples/`;
  idempotência (formatar duas vezes = uma); `--check` com exit 1/0.
- **Fase C**: `fs.stat`/`fs.rename` no diferencial do backend (ADR-0123); `glob` com tabela de
  padrões; `diff` com casos de CRLF, sem newline final e arquivo vazio.
- **Pacote**: `loxia add glob --git … --rev v0.1.0 --lock` em CI, `--frozen`/`--offline` com
  cache; `loxia doc` no repo do pacote.
- **Bench**: caso de formatação no `bench/` antes do flip (fase D).

Critério para revisitar: paridade atingida (fase D), `glob` com segundo consumidor, registry
existindo, ou o parser em Lox sendo reutilizado por outro tool (lint/LSP) — aí a extração
para pacote deixa de ser hipótese.

## Referências

- [ADR-0092](0092-estilo-e-formatter.md) — formato, referência Python e fase Lox.
- [ADR-0114](0114-ast-recuperada-para-tooling.md) — AST recuperada e CLI estrito.
- [ADR-0105](0105-dependencias-git.md) — `git` dep, lock e cache.
- [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md) — `std` reservado e raízes.
- [`docs/roadmap.md`](../roadmap.md) — self-hosting na fase Later.
- [`loxia/formatter.py`](../../loxia/formatter.py) — implementação de referência.
