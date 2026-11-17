# ADR-0088 — Distribuição: `loxia` como comando, stdlib embutida e raízes de módulo declaradas

- **Status:** accepted — **empacotamento entregue** em 2026-11-15 (wheel com `loxia`,
  `std/` e `runtime.c`; rename `src` → `loxia_core` feito) e **manifest/raízes
  entregues** em 2026-11-16 ([ADR-0100](0100-dependencias-path.md), que acrescenta
  `[dependencies] path` e a descoberta no ancestral).
- **Data:** 2026-11-15
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0073](0073-imports-modulos.md) (módulos e `_` privado),
  [ADR-0100](0100-dependencias-path.md) (dependências `path`),
  [ADR-0078](0078-nome-loxia-extensao-lx.md) (nome e `.lx`),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (nada de sintaxe nova aqui),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1/I3),
  [`../../IDEIAS.md`](../../IDEIAS.md) I-9 (opções), [`../../TODO.md`](../../TODO.md) §14
- **Implementação:** [`pyproject.toml`](../../pyproject.toml) (hatchling, `[project.scripts]`,
  force-include), [`loxia_core/bundle.py`](../../loxia_core/bundle.py),
  [`loxia_core/loader/manifest.py`](../../loxia_core/loader/manifest.py),
  [`loxia_core/loader/loader.py`](../../loxia_core/loader/loader.py),
  [`loxia_core/backend/driver.py`](../../loxia_core/backend/driver.py),
  [`tests/test_install.py`](../../tests/test_install.py),
  [`.github/workflows/release.yml`](../../.github/workflows/release.yml)

## Contexto

O projeto funciona a partir do clone e **não** funciona instalado:

- `pyproject.toml` não tem `[build-system]` nem `[project.scripts]` — `pip install loxia`
  não cria comando nenhum;
- `std/` fica fora do pacote Python e `STD_ROOT` resolve por
  `Path(__file__).resolve().parents[2] / "std"`, ou seja, a raiz do repo. No wheel, esse
  caminho não existe;
- a raiz de módulos é o diretório do arquivo de entrada; `..` e caminho absoluto são erro
  ([ADR-0073](0073-imports-modulos.md)). Logo, nenhum projeto consegue consumir código fora
  da própria pasta — nem um pacote instalado, nem um monorepo;
- o loader **inlina** módulos em compile-time (não há módulo em runtime), então os dois
  motores usam a mesma resolução. Isso é uma vantagem a preservar: o I1 não depende de um
  runtime de módulos.

A discussão completa de opções (vendor-only, raízes declaradas, registry com rede,
diretório global, `std` como pacote comum) está em [`../../IDEIAS.md`](../../IDEIAS.md) I-9.
As cinco decisões abaixo foram confirmadas pelo dono do projeto em 2026-11-15.

## Decisão

### 1. Um comando: `loxia`

`[project.scripts] loxia = "loxia.cli:main"`. As flags atuais (`--check`, `--emit`,
`--dump-ast`, `--debug`, `--version`, `-o/--output`, `--error-format`, `--max-heap`)
continuam válidas; subcomandos (`run`/`check`/`build`) entram como açúcar de CLI, não como
sintaxe da linguagem — logo **não** passam pelo portão do ADR-0066. Alvo completo na
[`../../TODO.md`](../../TODO.md) §6.9.

### 2. A stdlib viaja com o compilador

`std/` passa a ser **package data** em `loxia/std/` (ou incluído no wheel por
*force-include*). A resolução usa `importlib.resources` (`files("loxia") / "std"`), com
fallback para a raiz do repo em desenvolvimento. `std` é nome **reservado**: o usuário não
pode criar `std/` nem sombrear o bundle. A versão da stdlib é a versão do compilador — não
há semver independente na v1.

### 3. `loxia.toml` declara raízes; sem manifest, comportamento atual

```toml
[package]
name = "meu-app"

[modules]
paths = ["vendor", "../shared"]   # relativo ao manifest; ordem = precedência
```

Ordem de resolução, fixa: **projeto → `paths` na ordem declarada → `std`** (sempre por
último). Se dois roots contêm o mesmo caminho, é **erro explícito** — nunca "primeira
vence" em silêncio. Sem `loxia.toml`, a raiz é só o diretório do arquivo de entrada: o
comportamento de hoje continua valendo, e a mudança é aditiva.

### 4. `..` continua proibido no `import`; permitido só como raiz declarada

O statement `import` só aceita caminho de identificadores (`import acme.foo`). A raiz pode
morar fora do projeto **apenas** se declarada no manifest — explícita, versionada e
auditável. Assim o monorepo funciona sem que um fonte consiga escapar da raiz por conta
própria.

> **Nota (ADR-0100):** além de `[modules].paths`, o manifest ganhou
> `[dependencies] nome = { path = "..." }` e a descoberta no ancestral mais próximo. A
> ordem virou **projeto → dependência casada → `paths` → `--module-path` → `std`**; a
> dependência resolve o próprio pacote e não enxerga o projeto.

### 5. Determinismo e ambiente

- **Sem variável de ambiente** para caminho de módulo: quebraria o I3. Desenvolvimento usa
  `--module-path DIR` (repetível), e flags fazem parte do contrato "mesmas flags ⇒ mesmos
  bytes".
- Diagnósticos de resolução listam as raízes **relativas** ao projeto, nunca caminho
  absoluto.
- Ordem de resolução fixa; nada de paralelismo que mude precedência.
- Na v1, só o projeto raiz declara dependências; um pacote não declara as próprias.
- Symlink que escapa da raiz é erro na resolução.

## Consequências

### Positivas

- `pip install loxia` passa a entregar **comando + stdlib**; um programa roda de qualquer
  diretório sem clone, sem `uv`, sem `libgc` (só `std`).
- Monorepo e dependência vendorizada deixam de ser impossíveis sem abrir mão da regra de
  segurança: o que é proibido é o caminho escondido no fonte, não o root declarado.
- Uma resolução só para tree-walk e backend; o corpus `t1`/`t2` passa a poder rodar
  instalado.
- Ambiguidade vira erro — o contrário de "funciona na minha máquina".

### Negativas / custos

- **`src` era um pacote top-level no wheel.** *(Resolvido: renomeado para `loxia_core`;
  o parágrafo fica como registro do custo.)* O código importava `from src.frontend...`, então
  instalar a Loxia coloca um pacote chamado `src` no `site-packages` — feio e sujeito a
  colisão. Fechar isso exige renomear `src` para algo como `loxia_core` (refactor grande);
  fica registrado como dívida explícita, não como surpresa.
- **Mais um arquivo de configuração.** Manifest sem schema validado é fonte de erro; a
  validação (chaves desconhecidas, caminho inexistente) precisa de mensagens claras.
- **Precedência vira API.** Mudar a ordem depois quebra projetos; por isso a ordem é
  decidida agora e testada.
- **Build do wheel** passa a depender de um backend (`hatchling`/`uv_build`) no ambiente de
  release — mais um item de supply chain (já previsto na §14.1).
- **A stdlib deixa de ser editável no lugar** em instalações normais; desenvolvimento
  continua via fallback do repo.

### Neutras

- Nada muda na semântica da linguagem; zero sintaxe nova.
- `vendor` continua funcionando como pasta normal do projeto, sem manifest.
- O gerenciador de pacotes (fetch/registry) fica **fora** deste ADR — ver
  [`../../IDEIAS.md`](../../IDEIAS.md) I-10 e [`../../TODO.md`](../../TODO.md) §14.7.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só vendor (copiar dependências) | Mantido como fallback, mas não resolve monorepo nem wheel; não é distribuição. |
| Diretório global de pacotes (`~/.loxia/...`) | Estado fora do projeto quebra reprodutibilidade sem lockfile; difícil de depurar. |
| `std` como pacote comum, versionável | Versão da std divergir do compilador quebra semântica e I1; a std é parte da linguagem. |
| `LOXIA_PATH` (env) | Resultado passaria a depender do ambiente — viola I3. |
| `../` liberado no `import` | Caminho invisível no fonte, não auditável; a raiz declarada resolve o mesmo caso de forma explícita. |
| Registry com rede agora | Outro produto; sem ecossistema é resolver problema que não existe. Fases em I-10. |

## Como verificar

- `tests/test_install.py`: `uv build` → instalar o wheel num venv **fora** do repo →
  `loxia --version` → programa que importa `std.json` roda.
- `tests/test_manifest.py`: dependência `path`, monorepo com `../shared`, raiz ambígua
  (duas raízes com o mesmo módulo), `import ..x`/caminho absoluto, `std` reservado e
  `--module-path`; `tests/test_backend.py` cobre a paridade I1.
- `make check` verde e corpus `t1`/`t2` verde com o layout instalado.
- Revisitar se o rename `loxia_core` → layout `src/` de projeto entrar na fila, ou se o formato do
  manifest mudar.
