# ADR-0129 — Oráculo do front-end: AST por arquivo, JSON v1 e snapshot

- **Status:** accepted (implemented)
- **Data:** 2026-11-21
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0124](0124-fmt-self-host-e-pacotes-por-repo.md) (fase A do parser em
  Lox), [ADR-0114](0114-ast-recuperada-para-tooling.md) (AST recuperada e CLI estrito),
  [ADR-0075](0075-diagnosticos-estruturados.md) (diagnóstico estruturado),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4), [`docs/roadmap.md`](../roadmap.md)
- **Implementação:** `loxia_core/frontend/ast_json.py`, `loxia_core/frontend/spans.py`
  (`span_of_token_exact`), `loxia/engine.py` (`parse_file`/`dump_ast`), `loxia/cli_args.py`,
  `schema/ast-v1.json`, `tools/oracle_snapshot.py`, `tests/oracle/frontend.json`,
  `tests/test_ast_json.py` e `tests/test_frontend_oracle.py`

## Contexto

O [ADR-0124](0124-fmt-self-host-e-pacotes-por-repo.md) define a fase A como scanner + AST +
parser em Lox, com o `loxia ast` como oráculo: "árvore idêntica" e, para erros, "posição e
mensagem". O oráculo atual não permite essa comparação:

- `loxia ast` roda o **programa inteiro**: `_parse` carrega módulos e o loader renomeia
  símbolos (`std$strings$trim`). Em um arquivo com `import`, a saída começa pela AST da
  stdlib, não pela do arquivo. Dos 333 arquivos de `std/`, `tests/cases/` e `examples/`,
  **35 têm `import`** e não podem ser comparados por arquivo.
- a única saída de máquina é a S-expression do `AstPrinter`, declarada dump de debug
  ([`ast_printer.py`](../../loxia_core/frontend/ast_printer.py)). Ela não carrega spans, não
  distingue `fn` opcional de `fn` escrito, não expõe `params_end`/`arg_ends` (dos quais o
  formatter depende) e não é versionada.
- não havia snapshot do oráculo. Uma mudança no front Python feita para agradar o port
  alteraria AST, formatter ou diagnóstico sem diff visível.
- os 98 casos de `tests/cases/errors/` só são checados por substring de mensagem no runner
  golden; `file:line:col` e o código estável não entram na checagem. Desses, 77 falham no
  `--check` (não executam) e 21 são erros de runtime check-clean.

Sem um contrato de máquina, a fase A não consegue provar paridade e o dogfood vira uma
reescrita silenciosa do oráculo.

## Decisão

### 1. `--file-only` é o modo de oráculo; o padrão não muda

`loxia ast --file-only` transforma **exatamente um arquivo**, sem loader, sem resolução de
`import` e sem mangling. O padrão de `loxia ast` continua o programa inteiro (compatível), e
`--file-only` também vale para o modo legado `--dump-ast`.

### 2. `--format=json` v1 é o contrato de máquina e exige `--file-only`

`loxia ast --file-only --format=json` emite um envelope versionado (`schema_version: 1`,
`schema/ast-v1.json`):

```text
{
  "schema_version": 1,
  "kind": "program",
  "file": "tests/cases/arithmetic.lx",
  "statements": [
    { "kind": "expression", "span": { "start": { "...": 0 }, "end": { "...": 12 } },
      "expression": { "kind": "call", "span": { "...": 0 }, "callee": { "...": 0 },
        "paren": { "type": "RIGHT_PAREN", "lexeme": ")", "span": { "...": 0 } },
        "arguments": [ { "...": 0 } ], "optional": false, "spread": false,
        "commas": [], "arg_ends": [] } }
  ],
  "tokens": [
    { "type": "IDENTIFIER", "lexeme": "print", "literal": null, "doc": null,
      "span": { "start": { "line": 1, "column": 1, "offset": 0 },
                "end": { "line": 1, "column": 6, "offset": 5 } } }
  ]
}
```

Regras:

- `span.start`/`end` são half-open; `column` é 1-based em code points e `offset` 0-based em
  bytes UTF-8. O fim do token é calculado pelo lexema inteiro, inclusive strings
  multi-linha (`span_of_token_exact`); spans de nó são o menor intervalo que contém os
  tokens do nó (ou `null` quando não há token).
- o array `tokens` é completo (inclusive `EOF`, `doc` e `literal`); tokens embutidos nos nós
  carregam só `type`/`lexeme`/`span`. Presença de `fn_token`, `params_end`, `arg_ends`,
  `commas`, brackets e `optional` fica explícita — é o que o formatter usa.
- `Ty` é serializado na forma canônica de `display()` (`List[Int]`, `T: Ord`, uniões).
- `--format=json` sem `--file-only` é erro de CLI (exit 2): JSON e S-expression não podem
  descrever árvores diferentes.
- a saída é determinística e não contém caminho absoluto, PID, timestamp nem ordem de
  `set`/`dict`. Floats não finitos viram `"inf"`/`"-inf"`/`"nan"` (JSON estrito não os tem).
- `schema_version` só muda em quebra do contrato.

### 3. Snapshot congela AST, formatter e diagnósticos

`tools/oracle_snapshot.py` percorre `std/`, `tests/cases/` e `examples/` e grava
`tests/oracle/frontend.json`:

- hash canônico do JSON da AST para cada arquivo parseável (304 hoje) e a lista declarada de
  arquivos que não parseiam (29);
- hash dos bytes do `format_source` (o formatter Python é a referência do ADR-0092) e a
  exigência de que parser e formatter aceitem/recusem o mesmo conjunto;
- diagnósticos estruturados `(phase, code, severity, span)` dos 98 casos de erro.

`tests/test_frontend_oracle.py` falha quando o manifesto diverge; `make oracle-update`
regrava. Atualizar o snapshot é revisão consciente, não `pytest -k` verde.

### 4. O Python é o oráculo; o Lox nunca vira expectativa

O port em Lox é comparado contra a saída do Python (AST, bytes do formatter e diagnósticos).
Divergência é bug do Lox. Uma mudança no front Python que altere qualquer uma das três
superfícies precisa do diff do snapshot no mesmo PR; não se "conserta" o manifesto para o
Lox passar.

## Consequências

### Positivas

- A fase A passa a ter um alvo mensurável nos 333 arquivos, inclusive os 35 com `import`.
- Spans e detalhes de fonte entram no contrato; a paridade cobre posição, não só forma.
- Qualquer drift do oráculo aparece como diff de hash/diagnóstico no PR, não como bug
  descoberto na fase B.
- O mesmo JSON serve ao MCP/LSP e a inspeção manual (`loxia ast --file-only --format=json`).

### Negativas / custos

- O manifesto é hash para AST/formatter: o diff mostra **que** mudou, não **o que**; para
  inspecionar, rode o comando no arquivo. Os 98 diagnósticos são legíveis.
- Toda mudança de parser/formatter/corpus exige `make oracle-update` e revisão do diff; é
  atrito deliberado.
- O JSON é verboso (tokens completos + tokens embutidos); é saída de ferramenta, não formato
  de armazenamento.
- O snapshot não substitui o diferencial nativo (I1) nem o `--check` (I4); ele congela o
  **front**.

### Neutras

- `loxia ast` sem flags continua produzindo a S-expression e carregando módulos.
- `AstPrinter` continua sendo o dump de debug; o JSON é um módulo separado.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Usar só a S-expression | Perde spans, `fn` opcional, `params_end`/`arg_ends` e offsets; não serve à fase B. |
| Tornar o `AstPrinter` o contrato | É formato de debug, sem versão e sem os detalhes de fonte; congelaria a ferramenta errada. |
| `--format=json` implicar `--file-only` | Mágica; o usuário não veria que a árvore deixou de ser o programa inteiro. |
| Snapshot com JSON completo de 304 arquivos | Dezenas de MB no repositório e diff ilegível; hash + comando sob demanda resolve. |
| Esperar a fase B para criar o snapshot | O port começaria sem linha de base; o primeiro diff já seria ambíguo. |

## Como verificar

```bash
uv run main.py ast --file-only --format=json tests/cases/arithmetic.lx
uv run main.py ast --format=json tests/cases/arithmetic.lx   # exit 2, exige --file-only
uv run pytest tests/test_ast_json.py tests/test_frontend_oracle.py
make oracle          # confere o manifesto
make oracle-update   # regrava (revisar o diff)
```

Critério para revisitar: o parser em Lox precisar de informação que o JSON não expõe
(comentários/trivia, por exemplo) ou o custo de atualizar o manifesto passar a esconder
mudanças. Nesse caso, o ADR é atualizado antes de mudar o contrato.

## Referências

- [ADR-0124](0124-fmt-self-host-e-pacotes-por-repo.md) — fases A–D e o oráculo Python.
- [ADR-0114](0114-ast-recuperada-para-tooling.md) — AST recuperada e CLI estrito.
- [ADR-0075](0075-diagnosticos-estruturados.md) — envelope de diagnóstico v1.
- [`docs/spec/garantias.md`](../spec/garantias.md) — I1–I4.
- [`docs/tech/arquitetura.md`](../tech/arquitetura.md) — mapa de módulos.
