# ADR-0118 — TOML no toolchain: dados na linguagem, edição na ferramenta

- **Status:** accepted (implementação: editor do #8 entregue; spike de `std.toml` pendente)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0100](0100-dependencias-path.md) (dependências `path`),
  [ADR-0104](0104-lock-e-frozen.md) (lock, `--frozen`), [ADR-0105](0105-dependencias-git.md)
  (git, cache, fetch), [ADR-0072](0072-stdlib-batteries.md) (stdlib),
  [ADR-0071](0071-primitivas-de-runtime.md) (kernel), [ADR-0016](0016-api-stdlib-hibrida.md)
  (API da stdlib), [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (contrato do CLI),
  [ADR-0075](0075-diagnosticos-estruturados.md) (`C0004`),
  [#8](https://github.com/loxia-lang/loxia/issues/8),
  [#16](https://github.com/loxia-lang/loxia/issues/16) (`fs.open`), [`../roadmap.md`](../roadmap.md)
- **Implementação:** `loxia/manifest_edit.py`, `loxia/cli_commands.py` (`add`/`remove`),
  `tests/test_manifest_edit.py`, `tests/test_dependencies.py`; pendentes
  `tests/test_toml_parity.py` e `tests/lox/toml/` (spike #53)

## Contexto

A issue [#8](https://github.com/loxia-lang/loxia/issues/8) é o último pedaço do gerenciador
de dependências: `loxia add`/`remove` precisam editar `loxia.toml` **preservando comentários
e ordem** e então atualizar o lock. Resolução e artefatos já existem: dependência `path`
([ADR-0100](0100-dependencias-path.md)), lock com hash de árvore e `--frozen`
([ADR-0104](0104-lock-e-frozen.md)) e dependência `git` com rev/commit e cache
([ADR-0105](0105-dependencias-git.md)). O bloqueio é só a **escrita**.

Três fatos delimitam o problema:

1. O Python tem `tomllib`, que é **somente leitura** — e isso é deliberado na biblioteca
   padrão: serializar TOML canônico é fácil, **editar preservando trivia não é**.
2. Existem **duas necessidades diferentes** de TOML no toolchain: *dados* (ler manifest,
   emitir lock canônico) e *edição* (inserir/remover uma chave sem tocar no resto do
   arquivo). A segunda é um modelo de documento (comentários, espaços, ordem), não uma
   biblioteca de dados; no ecossistema Rust ela existe como crate separada (`toml_edit`),
   não na stdlib.
3. Na linguagem, TOML **completo é impossível**: `inf`/`nan` não são representáveis
   (`Float.parse` exige finito e divisão por zero é erro) e não há tipo de data. Logo
   qualquer `std.toml` é necessariamente um **subconjunto documentado**.

Requisitos de kernel: **nenhum novo**. O kernel já expõe `io.readFile`, `io.writeFile`,
`fs.exists` e `fs.listDir`; parser/writer são Lox puro. A decisão não move o orçamento de
primitivas ([ADR-0071](0071-primitivas-de-runtime.md)).

O self-host do CLI está em *Later* no [`../roadmap.md`](../roadmap.md), atrás do self-host
do formatter e da decisão de `fs.open` ([#16](https://github.com/loxia-lang/loxia/issues/16)).
Ele precisará de `parse` (ler manifest) e de `write` canônico (emitir lock) — mas
continuará precisando de edição com trivia para `add`, que `std.toml` não fornece.

## Decisão

### 1. Edição do manifest é da ferramenta, não da linguagem

`loxia add`/`remove` usam um **editor escopado** em Python (`loxia/manifest_edit.py`): um
modelo de linhas que localiza o span de `[dependencies]`, acha a entrada e substitui apenas
aquela linha. A linguagem não ganha API de edição preservando comentário — nem agora, nem
no self-host.

- Formas aceitas na v1: `nome = { path = "…" }` e `nome = { git = "…", rev = "…" }`
  (inline tables de uma linha; TOML 1.0 proíbe newline dentro de inline table).
- Formas fora disso (dotted keys, `[dependencies.nome]`, arrays/valores multilinha) são
  **recusadas** com diagnóstico `C0004` e o trecho na mensagem; o editor nunca adivinha.
  (Erratum: o ADR nasceu com `C0003`, mas o catálogo já usava esse código para
  scaffolding — ADR-0106; edição de manifest é `C0004`.)
- Entrada nova entra no **fim** da tabela (ordem preservada, como a issue pede); sem
  `[dependencies]`, a tabela é anexada ao fim do arquivo.
- `remove` apaga a linha da entrada; a tabela vazia permanece (TOML aceita).

### 2. Invariantes de segurança do editor

1. **Re-parse antes de gravar**: depois da edição em memória, o texto passa por
   `parse_manifest`; se falhar, aborta sem tocar no disco. Arquivo corrompido pelo editor
   fica impossível por construção.
2. **Escrita atômica** (temporário na mesma pasta + `os.replace`).
3. **CRLF e ausência de newline final preservados** (leitura/escrita com `newline=""`);
   linhas novas usam o terminador detectado no arquivo.
4. **Nada de rede**: a edição é local; `--lock` é opt-in e só ele pode clonar.

### 3. Contrato do `add`/`remove`

- `loxia add NAME --path DIR` ou `loxia add NAME --git URL --rev REV`; `remove NAME`.
- Sem rede por padrão: o comando edita e lembra `loxia lock`; `--lock` encadeia o lock
  (e é a única forma de `add` tocar a rede, preservando a tabela do
  [ADR-0105](0105-dependencias-git.md) §4).
- **Idempotência**: mesma spec já declarada ⇒ no-op, `exit 0`, `--json` com
  `"changed": false`. Spec diferente para o mesmo nome ⇒ erro `exit 65`, sem escrita.
- `--dry-run` imprime unified diff com caminho **relativo** (`loxia.toml`) e **sem
  timestamp** (I3); não escreve.
- Diagnóstico `C0004` para “manifest não editável com segurança”, separado de `E1001`
  (TOML inválido); exit `65`.
- Nome já declarado, `remove` de nome inexistente e spec inválida reusam as validações de
  `parse_manifest` — nenhuma regra duplicada no CLI.

### 4. TOML como **dados** é candidato à stdlib, mas por spike

`std.toml` (parse + write canônico) fica **adiado**; o primeiro passo é um spike em Lox, em
`tests/lox/toml/`, com:

- parser e writer canônico no subconjunto declarado (item 5);
- **corpus de paridade** contra `tomllib` no CI: para cada fixture, aceitar/rejeitar igual e
  comparar a estrutura (dump canônico ordenado); negativos (datas, `inf`, chave duplicada)
  exigem a mesma classificação e mensagem com linha/coluna;
- critério de promoção explícito (item 6).

O spike não é `std.` e não entra no corpus I1; é código de linguagem em teste, com harness
Python — o mesmo padrão de `tests/test_protocol_lox.py`.

### 5. Subconjunto declarado

A v1 aceita o que manifest e lock usam: tabelas e subtabelas, `[[array of tables]]`,
inline tables, arrays (inclusive multilinha e com vírgula final), strings básicas, literais
e multilinha, inteiros (decimal, `0x`, `0o`, `0b`, `_`), floats com expoente e `_`, bools e
comentários. **Fora**: datas/horas (sem tipo na linguagem) e `inf`/`nan` (irrepresentáveis).
O que ficar de fora é erro com linha/coluna — nunca valor silenciosamente errado (I2).

### 6. Promoção a `std/toml.lx` só com consumidor

Promover exige os quatro: paridade verde no subconjunto; um consumidor real (primeiro
programa Lox que lê config, ou o início do self-host); entrada de corpus I1 (`t2` em
`tests/corpus_manifest.py`); ADR do subconjunto com a página em `docs/stdlib/`.

## Consequências

### Positivas

- A #8 destrava sem dependência nova e sem esperar TOML na linguagem.
- Uma responsabilidade por camada: dados na linguagem (quando doer), edição na ferramenta.
- Kernel intocado; nenhuma primitiva nova.
- O spike nasce com harness de paridade, então as duas implementações não podem divergir
  em silêncio.
- Quando nascer, `std.toml` serve primeiro ao **lock** (write canônico), que é o artefato
  determinístico, e não ao `add`.

### Negativas / custos

- Durante o spike existem duas implementações de TOML (Python e Lox) — o custo é o corpus
  de paridade e a disciplina de mantê-lo.
- O subconjunto recusa TOML válido (datas, `inf`/`nan`); é uma limitação declarada, não um
  bug, e pode surpreender quem chega com arquivo de fora.
- `add` carrega um editor escopado só dele; o self-host vai reimplementá-lo em Lox como
  biblioteca da ferramenta (não como stdlib), duplicando trabalho uma vez.
- `C0004` é um código a mais no catálogo e precisa entrar em `docs/spec/erros.md` quando o
  produtor existir.

### Neutras

- `--lock` opt-in deixa o fluxo em dois passos para quem tem dependência `git`.
- O editor preserva o estilo existente, mas entradas novas saem sempre na forma canônica
  inline; quem usa outro estilo recebe `C0004` e edita à mão (ou usa `--rewrite` no futuro,
  se doer).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `tomllib` + reescrita canônica do arquivo | perde comentários e ordem; falha o aceite da #8 |
| Vendorizar `tomlkit` | primeira dependência de runtime para um comando; contraria “libs exigem conversa” |
| `std.toml` agora, sem spike | congela subconjunto antes de saber onde ele quebra, com consumidor inexistente |
| `std.toml` incluindo modelo de documento | escala de `toml_edit` (~milhares de linhas); acopla a ferramenta à linguagem |
| TOML como primitiva de kernel | o kernel não é o gargalo: `io.readFile`/`io.writeFile` bastam |
| Deixar `add` de fora e só documentar edição manual | é o estado atual; a dor da #8 é real |

## Como verificar

- `tests/test_manifest_edit.py`: comentários e ordem intactos, CRLF, arquivo sem
  `[dependencies]`, entrada existente (no-op), spec diferente (erro sem escrita), forma
  exótica (`C0004` sem tocar no disco), atomicidade em falha de re-parse.
- `tests/test_dependencies.py`: `add → lock → run`; `remove` + `lock --check` acusando
  drift; `--dry-run` não escreve.
- `tests/test_determinism.py`: `--dry-run`/`--json` sem caminho absoluto nem timestamp.
- Spike: `tests/test_toml_parity.py` verde no corpus.
- **Revisitar** se: `add` precisar editar formas além das inline (reavaliar documento vs
  vendor); o spike recusar TOML comum (corrigir o subconjunto antes de promover); ou o
  self-host do CLI começar (o editor vira biblioteca Lox da ferramenta, e aí a promoção de
  `std.toml` deixa de ser opcional).

## Referências

- Issue [#8](https://github.com/loxia-lang/loxia/issues/8) — `loxia add`/`remove`.
- Issue [#16](https://github.com/loxia-lang/loxia/issues/16) — decisão de `fs.open`.
- [ADR-0100](0100-dependencias-path.md), [ADR-0104](0104-lock-e-frozen.md),
  [ADR-0105](0105-dependencias-git.md) — dependências, lock e git.
- [ADR-0072](0072-stdlib-batteries.md) — critério de stdlib; [ADR-0071](0071-primitivas-de-runtime.md)
  — orçamento de kernel.
- [ADR-0093](0093-cli-agent-friendly-e-reparo.md) — contrato agent-friendly (`--json`,
  exit codes); [ADR-0075](0075-diagnosticos-estruturados.md) — códigos de diagnóstico.
- [`../roadmap.md`](../roadmap.md) — self-host em *Later*.
