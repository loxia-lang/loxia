# ADR-0128 — Contrato de motores: core, ambient e native-only

- **Status:** accepted
- **Data:** 2026-11-21
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (portão e invariantes),
  [ADR-0059](0059-i4-check-limpo-compila.md) (I4 e recusa do backend),
  [ADR-0071](0071-primitivas-de-runtime.md) (kernel sem FFI), [ADR-0072](0072-stdlib-batteries.md)
  (stdlib e ambient), [ADR-0075](0075-diagnosticos-estruturados.md) (catálogo de códigos),
  [ADR-0121](0121-matriz-de-cobertura-de-features.md) (matriz), [ADR-0123](0123-orcamento-do-kernel-por-grupo.md)
  (orçamento), [ADR-0125](0125-bytes-tipo-binario.md) (`Bytes`), [ADR-0126](0126-modulo-nativo-embutido-sqlite.md)
  (SQLite e callbacks), [ADR-0127](0127-pacotes-com-codigo-nativo.md) (pacotes nativos),
  [ADR-0119](0119-fs-open-handles-e-erro-de-host.md) (sandbox), [ADR-0037](0037-async-direcao.md)
  (async/threads)
- **Implementação:** `docs/spec/garantias.md`, `loxia/engine.py`, `loxia_core/loader/`,
  `loxia_core/execution/primitives.py` (metadado de camada), `loxia_core/diagnostics/codes.py`
  (código novo), `loxia/cli_commands.py` (`capabilities`), `tests/test_layers.py` (novo)

## Contexto

A pergunta "e se abandonarmos o oráculo e deixarmos o resto nativo?" volta a cada feature que
o interpretador não faz bem: callbacks, threads, ponteiros, FFI. A resposta atual é
informal — parte do código é **core** (I1), parte é **ambient** ([ADR-0072 §5](0072-stdlib-batteries.md)),
e o [ADR-0126](0126-modulo-nativo-embutido-sqlite.md)/[ADR-0127](0127-pacotes-com-codigo-nativo.md)
introduziram uma terceira categoria que ainda não tem nome, contrato nem diagnóstico.

Isso produz três problemas concretos:

- **Divergência silenciosa.** Sem uma regra, uma feature pode existir nos dois motores com
  semânticas diferentes; o usuário descobre em produção.
- **Assimetria de recusa.** O backend sabe dizer "não faço" (`E4001`, exit 65, I4). O
  interpretador não sabe — ele é o default (`loxia run`/REPL) e falharia de formas criativas.
- **Decisão sem registro.** "Native-only" fica sendo o que sobrou, não o que foi decidido; a
  pergunta volta na próxima feature e a resposta depende de quem responde.

O I1 não é o problema: ele cobre o corpus determinístico e já exclui ambient. O problema é
não existir contrato para o que fica **fora** do I1 por decisão, e não por acaso.

## Decisão

### 1. Três camadas, uma classificação por capacidade

| Camada | Promessa | Onde roda | Teste | Recusa |
| --- | --- | --- | --- | --- |
| **core** | I1 + I3: mesmos bytes nos dois motores | interpretador **e** nativo | corpus diferencial (`LEVELS`) | nenhuma |
| **ambient** | fora do I1/I3; comportamento declarado e testado com entrada fixa | onde o host permitir (um ou os dois) | teste próprio, sem caminho/timestamp/PID | sandbox, quando for o caso |
| **native-only** | **sem** promessa de equivalência; semântica só no binário | `--emit=exe` | golden do binário | **o interpretador recusa em compile-time** |

A classificação é por **capacidade**, não por binário: um módulo ambient pode ter uma API
native-only (ex.: `sqlite` ambient; `createFunction` native-only). O metadado fica no
primitivo/módulo, não no texto da doc.

### 2. A recusa é diagnóstico de primeira classe

O espelho do `E4001`:

```
error[E3021]: `sqlite.createFunction` is not supported by the interpreter; build with `--emit=exe`.
```

- Acontece **antes de executar** (compile-time), com exit **65**, apontando o call site.
- Código novo na faixa `E3xxx` (proposto: `E3021`), registrado em
  [`codes.py`](../../loxia_core/diagnostics/codes.py) e gerado em `docs/spec/erros.md` por
  `make codes` (o catálogo é fechado, [ADR-0075](0075-diagnosticos-estruturados.md)).
- `loxia check` é **agnóstico de motor**: aceita as três camadas (é o checker, não o
  executor). `run`/REPL recusam native-only; `build` recusa só a lacuna do backend (`E4001`,
  I4). Um `--target` explícito no `check` fica para quando houver consumidor (LSP/MCP).
- A recusa é **declarada**, nunca um erro de tipo inventado no lowering: o checker continua
  sendo a fonte única dos tipos (I4).

### 3. Metadado publicado, não prosa

- Cada primitiva/módulo declara `layer: core | ambient | native_only`.
- `loxia capabilities --json` publica `primitives` com `layer` (e `ambient`, `site`), junto do
  que o [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) já manda publicar.
- `docs/stdlib/` e `docs/spec/garantias.md` mostram a camada; a matriz do
  [ADR-0121](0121-matriz-de-cobertura-de-features.md) ganha a coluna de camada.
- Um teste (`tests/test_layers.py`) falha se alguma primitiva/módulo público não tiver
  camada, e se uma capacidade `core` não tiver caso no corpus.

### 4. Regra de admissão (antes de escrever código)

1. Default é **core**: exige as duas implementações e caso no corpus.
2. **native-only** exige justificativa de impossibilidade — "o interpretador **não
   consegue**", não "não quisemos implementar". Exemplos válidos: threads e modelo de
   memória; ponteiro cru/SIMD; callback C→Lox que reentra no runtime com estado de C;
   extensão de terceiro. Exemplo inválido: "é mais rápido no nativo".
3. **ambient** exige teste com entrada fixa e a declaração do que não é prometido (ordem de
   diretório, relógio, rede, banco).
4. **Nunca** a mesma feature com duas semânticas. Se os motores divergem, a feature é ambient
   ou native-only por declaração — não core por conveniência.

### 5. Consequência imediata: callbacks guardados são native-only

O guarda de callback do [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) (§6.1) é
**native-only** na v1: o interpretador usaria callables Python com tradução de exceção
diferente, e a promessa de equivalência não se sustenta. A recusa aponta o call site
(`sqlite.createFunction`), não o `import`.

### 6. Sandbox

`--sandbox` nega ambient e native-only por default (como `fs.open`/`sqlite3.*`); o que é
**puro** (core, ex.: `digest.sha256`) continua permitido. A camada entra na lista de negação
junto com o nome — uma capacidade nova não pode "esquecer" de nascer negada.

## Consequências

### Positivas

- Fim da divergência silenciosa: ou é core (I1), ou é declarado e recusado.
- O oráculo continua sendo o ativo (pega miscompile) sem virar freio de feature nativa.
- `run`/REPL deixam de ser cidadãos de segunda classe: eles **sabem** o que não fazem.
- A classificação vira dado (`capabilities --json`), então LSP/MCP/docs podem consumi-la.
- A decisão de cada feature passa a ter três respostas possíveis, com critério escrito.

### Negativas / custos

- Trabalho de classificação retroativa (33 primitivas + 29 módulos) e manutenção do metadado.
- Um código de diagnóstico novo e mais um caminho de recusa para testar.
- `check` aceitar tudo pode confundir quem espera que ele pegue "isso não roda no run";
  a resposta é o `run` recusar cedo, e o LSP mostrar a camada.
- native-only cria duas classes de programas; a documentação precisa ser explícita sobre
  qual comando roda o quê.
- A matriz de cobertura cresce (camada × caso), e o teste de "core tem corpus" pode ficar
  burocrático se a camada for mal atribuída.

### Neutras

- O I1 não muda de texto: muda de **escopo declarado** (core), o que já era a prática.
- A camada não afeta o orçamento do kernel; afeta a documentação e o diagnóstico.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Abandonar o oráculo e deixar o binário ser a spec | Miscompile silencioso, LSP/`run`/REPL divergentes, e o diferencial que já existe vira peso morto; o custo do interpretador é baixo nas features discutidas (Python `bytes`, `sqlite3`, Lox puro). |
| Tudo native-only | Perde a spec executável e a confiança para otimizar; o REPL e o `run` morrem como caminho real. |
| Manter informal (status quo) | A pergunta volta a cada feature e a resposta depende de quem responde; é o problema que este ADR fecha. |
| `--target` obrigatório no `check` | Cerimônia para o caso comum; fica para quando LSP/MCP precisarem. |
| Recusar native-only com erro de tipo no checker | Inventa regra de tipo fora do checker e cria diagnóstico enganoso; a recusa é de motor, não de tipo. |

## Como verificar

- `tests/test_layers.py`: toda primitiva/módulo público tem camada; capacidade `core` tem
  caso no corpus; `native_only` não aparece em `LEVELS`.
- Caso negativo: programa com `sqlite.createFunction` sob `run` → exit 65 com `E3021` e o
  call site; sob `--emit=exe` → compila e roda.
- `loxia capabilities --json` traz `layer` e o teste de contrato do CLI acompanha.
- `--sandbox` nega ambient/native-only e permite core puro (caso positivo e negativo).
- `docs/spec/garantias.md` e `docs/spec/erros.md` gerados/atualizados no mesmo PR.

Critério para revisitar: um `--target` no `check` (LSP/MCP), uma feature que precise de
semântica nova nos dois motores (vira core, com corpus), ou um caso em que native-only seja
a única saída para algo que o interpretador *poderia* fazer — aí a justificativa é reexaminada.

## Referências

- [ADR-0014](0014-identidade-e-invariantes.md) — invariantes e portão de admissão.
- [ADR-0059](0059-i4-check-limpo-compila.md) — recusa declarada do backend.
- [ADR-0072](0072-stdlib-batteries.md) — ambient e determinismo.
- [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) — módulo nativo e callbacks.
- [`docs/spec/garantias.md`](../spec/garantias.md) — texto do contrato.
