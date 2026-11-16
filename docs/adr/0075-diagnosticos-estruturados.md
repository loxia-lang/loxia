# ADR-0075 — Diagnósticos estruturados: modelo, códigos e renderizadores

> **Atualizado por** [ADR-0089](0089-stack-trace-de-runtime.md) (stack trace e
> `R1015` com posição) e [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (schema de
> `fixes[]`, loop de reparo, `C0001`/`W1xxx`, JSONL/watch). Os produtores de `fixes[]` e
> warnings continuam pendentes; o modelo e o envelope v1 não mudam.

- **Status:** accepted
- **Data:** 2026-11-14
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0003](0003-diagnosticos-por-execucao.md),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1/I3),
  [ADR-0026](0026-freeze-1.0.md), [ADR-0046](0046-closures-celulas-l4.md),
  [`../../IDEIAS.md`](../../IDEIAS.md) I-4,
  [`../../TODO.md`](../../TODO.md) §3
- **Implementação:** [`loxia_core/diagnostics/`](../../loxia_core/diagnostics/),
  [`loxia_core/frontend/tokens.py`](../../loxia_core/frontend/tokens.py),
  [`loxia_core/frontend/scanner.py`](../../loxia_core/frontend/scanner.py),
  [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py),
  [`loxia/cli.py`](../../loxia/cli.py), [`runtime/runtime.c`](../../runtime/runtime.c),
  [`tests/test_diagnostics.py`](../../tests/test_diagnostics.py),
  [`tests/test_determinism.py`](../../tests/test_determinism.py)

## Contexto

O `ErrorReporter` era um objeto por execução (ADR-0003) que **imprimia direto** e mantinha
quatro formatos ad-hoc:

- léxico: `[line N] Error: mensagem`;
- parser/resolver/checker: `[line N] Error at 'token': mensagem`;
- runtime: `mensagem` + `[line N]`;
- backend: `[line N] Error: mensagem`.

Não havia código estável, coluna, trecho de código nem um modelo que um editor ou agente
pudesse consumir. O desenho de "diagnósticos profissionais" existia no `TODO.md` §3.1, mas
a seção foi removida do arquivo (o texto sobrevive no histórico do git, em `052c55e^`). O
[`IDEIAS.md`](../../IDEIAS.md) I-4 manteve a ideia de erros estruturados determinísticos,
com envelope JSON, `code`, `span` e ordenação fixa. O [ADR-0046](0046-closures-celulas-l4.md)
registrou que spans/caret/stack trace ficavam **fora do L4** e exigiam decisão própria.

O que restringe o desenho:

1. **I1 inclui stderr byte a byte** entre tree-walk e binário
   ([`../spec/garantias.md`](../spec/garantias.md)); `tests/test_backend.py` compara os três
   canais. O binário só conhece `lox_panic(linha, mensagem)`.
2. A suíte oficial compara a **primeira linha** do erro de runtime com a mensagem do livro
   (`tests/test_official_suite.py`).
3. **I3** proíbe caminho absoluto, timestamp, PID, endereço e ordem instável na saída.

## Decisão

**Um modelo, renderizadores puros, códigos por família e saída determinística.**

### 1. Modelo

`Diagnostic` imutável (em `loxia_core/diagnostics/diagnostic.py`) com `code`, `phase`, `severity`,
`message`, `span`, `labels[]`, `notes[]`, `help`. `Span` tem arquivo e `start`/`end`
half-open; `Position` guarda `line` e `column` 1-based em **code points** e `offset`
0-based em **bytes UTF-8**. `Token` ganha `column` e `offset` (defaults preservam quem
constrói tokens à mão).

O reporter **só coleta**; `render.py` tem funções puras (`render_human`, `render_short`,
`render_runtime`, `render_json`) e o `Lox` decide stream e exit code. Isso materializa a
separação que o ADR-0003 já anunciava e permite testar diagnóstico sem capturar stderr.

### 2. Códigos estáveis por família

`Code` é um `StrEnum` tipado (`loxia_core/diagnostics/codes.py`), então **não é possível emitir um
código fora do catálogo** (mypy strict pega) e cada código tem uma fase fixa em
`CODE_PHASE`. Faixas:

| Faixa | Fase | Exemplos |
| --- | --- | --- |
| `E0xxx` | léxico | `E0001` caractere inesperado, `E0002` string não terminada |
| `E1xxx` | sintaxe | `E1001` token inesperado, `E1002` alvo de atribuição inválido |
| `E2xxx` | resolver | `E2001` variável duplicada, `E2002` atribuição a `val` |
| `E3xxx` | checker | `E3001` tipo incompatível, `E3002` aridade, `E3003` nome indefinido |
| `E4xxx` | backend | `E4001` não suportado pelo backend, `E4002` erro interno |
| `R1xxx` | runtime | `R1002` divisão por zero, `R1003` variável indefinida |

Códigos identificam **famílias**, não mensagens; o texto específico continua na mensagem.
`E3000` é o fallback semântico do checker para a cauda longa, e pode ser refinado em códigos
mais específicos sem reutilizar código. O catálogo é documentado em
[`../spec/erros.md`](../spec/erros.md) e um teste exige que todo membro de `Code` apareça
lá.

### 3. Formatos

`human` (padrão) — cabeçalho gcc/clang + trecho com caret:

```
exemplo.lox:3:7: error[E2001]: Already a variable with this name in this scope.
  |
3 |   var a = 2;
  |       ^
```

`short` — só o cabeçalho (uma linha, grepável): `exemplo.lox:3:7: error[E2001]: …`.

`json` — envelope v1 (uma linha de `schema_version`):

```json
{"schema_version":1,"command":"check","success":false,"exit_code":65,
 "diagnostics":[{"code":"E2001","phase":"resolver","severity":"error",
   "message":"…","span":{"file":"exemplo.lox",
     "start":{"line":3,"column":7,"offset":24},
     "end":{"line":3,"column":8,"offset":25}},
   "labels":[],"notes":[],"help":null}],
 "summary":{"errors":1,"warnings":0,"suppressed":0}}
```

`--error-format` aceita `human|short|json`; `--color=auto|always|never` (respeita
`NO_COLOR`); `--max-errors N` (default 20, `0` = ilimitado).

**Destino do JSON:** `check` → stdout; `run`, `build` e `ast` → stderr. `build --emit=ll`
já escreve o IR em stdout e `run` tem a saída do programa, então só `check` pode usar
stdout sem misturar canais. Para `check`/`build` o envelope sai mesmo no sucesso; para
`run` só quando há diagnóstico.

### 4. Determinismo

- Ordenação `(file, offset, line, column, code, message)`; dedup por `(code, span)`;
  limite `--max-errors` com contagem de suprimidos no JSON.
- Caminho de exibição: relativo ao CWD; se o arquivo estiver fora do CWD, só o basename.
  Nunca absoluto. Depende da invocação (CWD + argumento), que é determinística.
- Tab = 4 colunas; largura Unicode correta (combining = 0, CJK largo = 2) para o caret.
- JSON com ordem de chaves fixa; nada de timestamp/PID/endereço/ordem de `dict`.
- `tests/test_determinism.py` roda o CLI com dois `PYTHONHASHSEED` e exige bytes idênticos.

### 5. Runtime e I1

Os dois motores imprimem o **mesmo cabeçalho** da compilação para erro de runtime
(`arquivo:linha:col: error[R1xxx]: mensagem`), **sem caret** — o binário pode rodar sem a
fonte. A implementação saiu em dois commits:

1. modelo + códigos + `human`/`short`/`json` na compilação, com o runtime ainda em
   `mensagem` + `[line N]` (para não misturar renderização com ABI);
2. paridade nativa: `lox_panic(line, column, code, message)`, coluna nas ~25 funções do
   runtime, `lox_throw`/frames de `try` com coluna, `lox_init(source_path)` e o caminho de
   exibição embutido no build (como `__FILE__`), sempre relativo. O lowering passa o
   **mesmo token** que o tree-walk usaria, para linha/coluna/código baterem.

A suíte oficial compara a **mensagem contida** no stderr (critério do harness do livro),
não a primeira linha inteira. I1 continua comparando os três canais. Quando a posição é
sintética (campo interno como `message` da classe `Exception`), o cabeçalho degrada para
`error[CODIGO]: mensagem` nos dois motores.

### 6. Fora de escopo desta decisão

`fixes[]` com edições, `lox explain`, `lox capabilities`, `--json-lines`, stack trace de
runtime, proveniência em `notes` (ex.: "o valor vem de `pessoa.nome`"), warnings/`-Werror`
e LSP. O modelo tem espaço para eles; o contrato só nasce quando houver produtor confiável.
Um `fix` errado é pior do que nenhum.

> **Nota (ADR-0090/0093):** o LSP, o JSONL/watch, o timeout e os warnings ganharam
> contrato próprio; `fixes[]` tem schema/loop definidos no ADR-0093, mas **nenhum produtor**
> ainda. Esta seção continua valendo para o que não tem produtor.

## Consequências

### Positivas

- Um único modelo alimenta terminal, CI, editor e agente; a mensagem não é gerada duas vezes.
- Códigos estáveis e tipados dão um eixo de tooling sem proibir refinar mensagens.
- A ordem/limite determinísticos tornam o stderr comparável byte a byte e testável.
- O diagnóstico de compilação fica localizável (linha, coluna, caret) e o runtime mantém
  o contrato do livro.
- Testes de diagnóstico deixam de depender de `capsys`.

### Negativas / custos

- O reporter passa a exigir um `code` em toda emissão; a cauda longa do checker usa
  `E3000` até ser refinada.
- `Token` ganhou dois campos e o scanner passou a centralizar linha/coluna/offset em
  `_advance` (mais fácil de errar ao adicionar um consumo direto de `_current`).
- O `human` depende da fonte carregada; sem ela (erro de backend) degrada para `short`.
- A fase 2 mexe na ABI do runtime e obriga a revalidar o corpus I1 inteiro.

### Neutras

- O formato antigo `[line N] Error at 'x':` some dos erros de compilação; o
  `docs/spec/erros.md`, a suíte oficial e os testes foram adaptados no mesmo commit.
- `--error-format=json` não tem contraparte no binário gerado; o contrato cobre `lox run`.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Continuar imprimindo direto do scanner/parser | impossível ordenar/deduplicar/testar sem capturar stderr; era o status quo |
| Um código por mensagem (~150) | manutenção e catálogo grandes demais para o ganho; família cobre o uso |
| Classificar código por prefixo de mensagem | frágil: renomear uma mensagem mudaria o código em silêncio |
| Layout rustc (`error[...]` + `-->` em outra linha) | duas gramáticas de cabeçalho e pior para grep/editor; `pretty` pode entrar depois |
| Congelar o runtime para sempre | o erro de runtime é o caminho comum sem `--check` e ficaria sem código/coluna |
| Caret também no binário | exigiria embutir a fonte e duplicar o renderizador; risco alto de I1 |
| JSON sempre em stdout | `run` tem a saída do programa e `build --emit=ll` tem o IR em stdout |

## Como verificar

- `tests/test_diagnostics.py` — spans, caret com tab/Unicode, `short`, JSON, runtime.
- `tests/test_error_reporter.py` — dedup, ordem, cap, `mark/restore`, `lowerable`.
- `tests/test_cli.py` — `--error-format`, `--color`, `--max-errors`, destinos do JSON.
- `tests/test_determinism.py` — bytes idênticos em seeds diferentes, sem caminho absoluto.
- `tests/test_official_suite.py` e `tests/runner.py` — mensagens continuam casando.
- `tests/test_backend.py` — I1 nos três canais (fase 2 revalida o corpus inteiro).
- `make check`.

Critério para revisitar: quando `fixes[]`/`explain`/LSP entrarem; quando o runtime nativo
ganhar stack trace; se o `E3000` continuar aparecendo em erros comuns.

## Referências

- [`../spec/erros.md`](../spec/erros.md) — catálogo vivo.
- [`../spec/garantias.md`](../spec/garantias.md) — I1/I3.
- Rust: <https://rustc-dev-guide.rust-lang.org/diagnostics.html#json-output>
- LSP `Diagnostic`:
  <https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#diagnostic>
- SARIF: <https://sarifweb.azurewebsites.net/>
