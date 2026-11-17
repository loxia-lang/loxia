# ADR-0100 — Dependências `path` e resolução por nome de pacote

- **Status:** accepted (implementado)
- **Data:** 2026-11-16
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0073](0073-imports-modulos.md) (módulo = arquivo, `_`,
  `import`), [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md) (raízes e
  `loxia.toml`), [ADR-0066](0066-orcamento-e-gate-sintatico.md) (nada de `..` no fonte),
  [`../../IDEIAS.md`](../../IDEIAS.md) I-9/I-10
- **Implementação:** `loxia_core/loader/manifest.py`,
  `loxia_core/loader/loader.py`, `loxia/cli.py` (`--module-path`),
  `tests/test_manifest.py` e `tests/test_backend.py`

## Contexto

O [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md) decidiu que `loxia.toml` declara
raízes e que `..` continua proibido no `import`. Faltava o formato que um gerenciador de
dependências consegue emitir sem transformar o nome do diretório em API. Com
`[modules].paths` puro, `import acme.foo` resolve `<root>/acme/foo.lx`: renomear a pasta
`acme` no disco quebra o código, e um lockfile não tem como fixar a identidade do pacote.

O TODO §14.4 já pedia “resolver `import acme.foo` pelo pacote declarado, não pelo nome do
diretório”. Esta decisão fecha essa parte e deixa lock/git/registry fora.

## Decisão

### 1. `loxia.toml` é descoberto no ancestral mais próximo

O primeiro `loxia.toml` subindo do diretório do entry até a raiz vence; sem manifest, o
comportamento antigo continua (raiz = diretório do entry). A descoberta não usa variável
de ambiente nem CWD. Com manifest, a raiz do projeto é a **pasta do manifest**, então
rodar `proj/src/main.lx` resolve `import lib.foo` em `proj/lib/foo.lx`.

### 2. Dependência nomeada

```toml
[package]
name = "meu-app"

[dependencies]
acme = { path = "../acme" }

[modules]
paths = ["vendor"]
```

- A chave de `[dependencies]` é o **nome lógico** do pacote; `import acme.foo` procura
  `../acme/foo.lx`, não `../acme/acme/foo.lx`.
- `path` é relativo à pasta do manifest; precisa existir e ser diretório. Caminho
  absoluto é erro (manifest versionado não carrega caminho da máquina).
- Nome de dependência é identificador ASCII; `std` é reservado.
- Só o manifest do projeto declara dependências; um pacote dependente não declara as
  próprias na v1.
- `[modules].paths` continua existindo para raízes soltas (vendor/monorepo): são raízes
  de namespace, então `import shared.util` resolve `<root>/shared/util.lx`.
- `--module-path DIR` (repetível) é o escape de desenvolvimento; entra depois de
  `[modules].paths`, relativo ao CWD.

### 3. Ordem e isolamento

Ordem de candidatos para o **projeto**: `projeto` → dependência cujo primeiro segmento
casa (se houver) → `[modules].paths` na ordem → `--module-path` na ordem → `std`.
Candidatos existentes em mais de uma raiz são **erro de ambiguidade** (nunca
“primeira vence”); a mensagem lista as raízes e caminhos relativos.

Um módulo carregado de uma dependência resolve imports no **próprio pacote** (ou em
outra dependência declarada) e `std`; ele não enxerga o projeto nem as raízes soltas.
Assim `acme/util.lx` importa `acme.base` mesmo que o projeto tenha `acme/base.lx`, e um
`import segredo` dentro do pacote falha com uma mensagem que manda usar `acme.segredo`.

`std.*` é sempre o bundle, nunca um diretório do usuário. `import acme` (só o nome da
dependência) é erro: pacote é namespace, não módulo.

### 4. Nada de `..` no fonte

`import ..foo` continua erro de sintaxe. O caminho relativo só existe no `path` do
manifest ou no `--module-path`, que são explícitos, versionados (o manifest) e auditáveis.
O display dos diagnósticos usa o **nome lógico** (`acme/foo.lx`), então não depende de CWD
e nunca mostra caminho absoluto (I3).

### 5. Fora de escopo

`loxia.lock`, versão/semver, `git`, registry, cache e rede ficam para as fases 1–3 do
[`../../TODO.md`](../../TODO.md) §14.7. A resolução é compile-time e a mesma para
tree-walk/backend; não há runtime de módulos.

## Consequências

### Positivas

- O nome do pacote no `import` deixa de ser o nome do diretório; o gerenciador pode
  baixar `acme` em qualquer pasta e o lock pode fixar a identidade.
- Monorepo e dependência vendorizada funcionam sem `..` no fonte e sem rede.
- Ambiguidade e raiz inexistente falham cedo, com caminho relativo.
- Mesma resolução nos dois motores; nenhum lowering novo.

### Negativas / custos

- Mais um formato de manifest para validar; manifesto inválido bloqueia a execução.
- Dependência vê outras dependências declaradas pelo projeto (visibilidade plana na v1);
  dependência não declara as próprias dependências.
- `[package].name` ainda não é usado para auto-import do próprio projeto.
- O diretório do pacote precisa ser a raiz dos módulos; um layout `src/` exige apontar
  `path` para `src`.

### Neutras

- `[modules].paths` permanece para raízes sem nome; `[dependencies]` é o caminho
  recomendado quando há um pacote.
- `--module-path` é a válvula de desenvolvimento; o CI deve preferir manifest.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só `[modules].paths` | O nome do diretório vira contrato; lock/registry não têm identidade estável. |
| `import ..foo` no fonte | Reversão do ADR-0073/0088; caminho invisível, difícil de auditar e de versionar. |
| Caminho absoluto no manifest | Manifest versionado passaria a depender da máquina; quebra reprodutibilidade. |
| Dependência ver o projeto inteiro | Pacote dependeria de código não declarado; ambiguidade e acoplamento invisíveis. |
| Registry/lock agora | Sem pacote real e sem fetch, é outro produto; fases em I-10/§14.7. |

## Como verificar

- `uv run pytest tests/test_manifest.py` — dependência path, self-import, monorepo,
  discovery no ancestral, ambiguidade, isolamento, `--module-path`, manifest inválido,
  `std` reservado e `..` rejeitado.
- `uv run pytest tests/test_backend.py -m backend -k dependencia_path` — paridade I1.
- `make check` verde; `--check` limpo compila.

Critério para revisitar: quando entrar lock/git/registry, quando um pacote precisar
declarar dependências próprias ou quando `[package].name` tiver consumidor.

## Referências

- [`../spec/semantica.md`](../spec/semantica.md) — módulos e resolução.
- [ADR-0073](0073-imports-modulos.md), [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md).
- [`../../IDEIAS.md`](../../IDEIAS.md) I-9 (opções) e I-10 (gerenciador).
