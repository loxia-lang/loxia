# ADR-0106 — Scaffolding: `loxia new` e `loxia init`

- **Status:** accepted (implementado)
- **Data:** 2026-11-17
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (subcomandos),
  [ADR-0100](0100-dependencias-path.md)/[ADR-0104](0104-lock-e-frozen.md)/[ADR-0105](0105-dependencias-git.md)
  (manifest/lock), [`../../TODO.md`](../../TODO.md) §14.0/§14.7,
  [`../../IDEIAS.md`](../../IDEIAS.md) I-10
- **Implementação:** `loxia/scaffold.py`, `loxia/cli.py` (`new`/`init`),
  `tests/test_scaffold.py`

## Contexto

O primeiro contato com a linguagem exige criar à mão `loxia.toml`, `src/main.lx`,
`.gitignore` e o lock. O [`../../TODO.md`](../../TODO.md) §14.0 listava `loxia new` como
P3; sem scaffold o usuário (ou agente) precisa conhecer o manifest, o lock e as convenções
antes de rodar a primeira linha — e `loxia run` num arquivo solto não exercita
dependências/`--frozen`.

O `loxia add` chegou a ser considerado junto, mas editar `loxia.toml` sem um writer de
TOML que preserve comentários/ordem é arriscado; a decisão ficou adiada (ver §"Fora de
escopo").

## Decisão

### 1. Dois comandos, dois estados

- `loxia new NAME` — cria o diretório; falha se ele já existe (`init` é para isso).
- `loxia init [DIR]` — inicializa um diretório **existente** (default `.`); falha se ele
  já contém `loxia.toml`, `src/main.lx` ou `.gitignore`.

Nenhum dos dois sobrescreve arquivo. Diretórios intermediários de `new` são criados.

### 2. Template mínimo e determinístico

```
loxia.toml      [package] name + version = "0.1.0"
.gitignore      .loxia/  e dist/
src/main.lx     print("hello from <nome>")
loxia.lock      version = 1, sem pacotes
```

O lock vazio faz `loxia lock --check` e `loxia run --frozen` funcionarem de cara. Nada de
README/CI/LICENSE no template: são opinião demais e mais arquivos para manter; o que o
`--check` e o `run` precisam é só isso.

### 3. Nome do pacote

- Default: nome do diretório normalizado para identificador ASCII (`my-app` → `my_app`;
  iniciar com dígito ganha prefixo `app_`; vazio vira `app`).
- `--name NOME` sobrepõe e exige `[A-Za-z_][A-Za-z0-9_]*` (valor inválido é erro de uso,
  exit 2). O nome entra entre aspas no TOML e na mensagem de `src/main.lx`.

### 4. Git

- `git init -q` por padrão, **sem commit**; `--no-git` desliga.
- Se já existe um `.git` no alvo ou em qualquer ancestral, **não** cria repositório
  aninhado (monorepo/vendor continua um repo só).
- `git` ausente do `PATH` é erro `C0003` com a dica `--no-git`; em `new`, a falha remove o
  diretório recém-criado (nada de projeto pela metade).

### 5. Saída e diagnóstico

- Sucesso: uma linha (`Created project 'nome' at 'caminho'.` / `Initialized ...`), com
  caminho **relativo** (I3).
- `--json` publica `{path, name, files, git}` no stdout para tooling/agente.
- Erro de estado: `C0003` (fase `cli`, exit 65); nome inválido continua erro de uso (2).
  `C0003` é catálogo novo, gerado por `make codes`.

## Fora de escopo

- **`loxia add`**: `add nome --path DIR`/`--git URL --rev X` seria útil já sem registry
  (fase 3), mas editar o manifest preservando comentários/ordem exige um writer de TOML.
  Decisão: implementar `add` **depois** de uma stdlib de TOML; até lá o fluxo é editar o
  `loxia.toml` à mão e rodar `loxia lock`. Hoje o §13 lista YAML/TOML como **fora** da
  stdlib, então essa inclusão é uma decisão anterior, registrada em aberto no §11.
- `loxia remove` (par natural do `add`) e atualização de dependências.
- Scaffold completo (`cargo new` com README/CI/LICENSE) e templates alternativos
  (`--lib`, workspaces).
- Criar commit inicial, escolher branch default ou configurar remoto.

## Consequências

### Positivas

- Primeiro projeto em um comando, já com lock e `--frozen` funcionando.
- Template pequeno e determinístico (teste compara bytes entre dois projetos).
- Sem sobrescrita e sem repo aninhado: seguro em monorepo e em diretório existente.
- `--json` deixa o caminho pronto para agentes/MCP.

### Negativas / custos

- Mais um artefato de template para manter em passo com o manifest/lock.
- Nome normalizado pode surpreender (`my-app` vira `my_app`); documentado no help/ADR.
- `add` continua manual; a lacuna fica explícita no TODO.

### Neutras

- `git init` é silencioso e não cria commit; o usuário segue o fluxo de VCS que quiser.
- `init` em diretório não vazio é permitido, desde que não colida com os arquivos do
  template.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `new` sobrescrevendo diretório existente | Perda de dados silenciosa. |
| Template completo (README, CI, LICENSE) | Opinião e manutenção; o mínimo já roda. |
| `init` sempre criando `git init` | Repo aninhado em monorepo/vendor. |
| Exigir `--name` sempre | Atrito no caso comum; o diretório já dá um nome razoável. |
| Implementar `add` agora com edição textual de TOML | Frágil com comentários/ordem e sem writer na stdlib; decisão adiada. |

## Referências

- [`../../README.md`](../../README.md) — quick start e tabela de comandos.
- [`../../TODO.md`](../../TODO.md) §14.0 (tooling), §14.7 (fases) e §11 (TOML em aberto).
