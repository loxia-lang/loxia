# ADR-0089 — Stack trace de runtime: frames, call site e posição do R1015

- **Status:** accepted
- **Data:** 2026-11-15
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0075](0075-diagnosticos-estruturados.md) (modelo de
  diagnóstico), [ADR-0077](0077-limite-de-pilha.md) (limite de pilha e R1015),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1/I3),
  [ADR-0031](0031-backend-nativo.md) (contrato de panic do binário),
  [ADR-0046](0046-closures-celulas-l4.md) (spans/trace fora do L4),
  [ADR-0087](0087-heap-cap-e-self-hosting.md) (orçamentos)
- **Implementação:** [`loxia_core/diagnostics/`](../../loxia_core/diagnostics/),
  [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py),
  [`loxia_core/execution/limits.py`](../../loxia_core/execution/limits.py),
  [`loxia_core/backend/`](../../loxia_core/backend/),
  [`runtime/runtime.c`](../../runtime/runtime.c),
  [`tests/test_diagnostics.py`](../../tests/test_diagnostics.py),
  [`tests/cases/`](../../tests/cases/),
  [`tests/test_backend.py`](../../tests/test_backend.py)

## Contexto

O [ADR-0075](0075-diagnosticos-estruturados.md) entregou `Diagnostic` com código, fase,
span e `human`/`short`/`json`, mas deixou **stack trace** e **posição do R1015** fora de
escopo. O [ADR-0077](0077-limite-de-pilha.md) fechou o contador de 10.000 chamadas com
R1015 **sem linha/coluna** e registrou que frames continuavam trabalho separado. O
resultado prático: um erro de runtime em uma cadeia de chamadas dizia apenas onde o
`// 0` estava, não **como** o programa chegou ali; e `R1015` não dizia nem onde.

Três restrições mandam no desenho:

1. **I1 compara stderr byte a byte** entre tree-walk e binário. Qualquer frame impresso
   pelo interpretador precisa ser impresso igual pelo runtime C.
2. **I3** proíbe endereço, PID, timestamp, caminho absoluto e ordem instável.
3. O tree-walk é o oráculo: o trace não pode depender de introspecção do Python nem de
   informação que o binário não tenha.

O [ADR-0065](0065-hir-lite-controle.md) lista "stack trace com frames" como possível
gatilho de HIR-lite. Este ADR conclui que **não é**: um array de frames
`(nome, arquivo, call site)` alimentado em `lox_stack_enter`/`lox_stack_leave` resolve o
caso sem CFG, sem materializar frames e sem tocar no lowering de controle. O TODO §11.7
foi corrigido para remover essa menção.

## Decisão

**Stack trace default-on nos dois motores, com nome do chamado, call site, recorte
determinístico e o mesmo formato no binário.**

### 1. Formato

Depois do cabeçalho do erro de runtime, um frame por ativação Lox, **mais interno
primeiro**:

```text
mod.lx:2:12: error[R1002]: Division by zero not allowed
  at inner (main.lx:7:14)
  at outer (main.lx:9:3)
```

- `name` é o nome exibível do **chamado**: `display_name` da declaração (sem mangling de
  módulo), `init`, `<lambda>` ou o nome da classe para o construtor. Não qualificamos com
  `C.`/módulo: o arquivo do call site já desambigua e mantém a paridade simples.
- A posição do frame é o **call site** (onde aquela ativação foi chamada), não a
  declaração. O topo (código do script) não é frame.
- O R1015 usa a posição da **declaração** do chamado que estourou (o próximo frame não
  chegou a existir) e lista os frames ativos.

### 2. Recorte determinístico

`TRACE_HEAD = 5` e `TRACE_TAIL = 5` em
[`limits.py`](../../loxia_core/execution/limits.py); o driver passa os mesmos números ao
runtime C por `-D`. Acima de 10 frames: os 5 mais internos, `  ... N frames omitted` e os 5
mais externos. Sem endereço, sem hash, sem ordem de `dict`.

### 3. Modelo e formatos

`Diagnostic.trace: Trace | None`, com `Trace(frames, omitted, head)` e
`Frame(name, file, line, column)`:

- `human` imprime os frames depois do cabeçalho (sem caret no runtime: o binário pode
  rodar sem a fonte);
- `short` continua **uma linha** por diagnóstico e omite o trace;
- `json` expõe `"trace": {"frames": [...], "omitted": N, "head": H}`, `null` quando não é
  runtime. `head` só é significativo com `omitted > 0`.
- O binário imprime sempre o formato humano; `--error-format` não atravessa o executável.

### 4. Quem captura o trace

No tree-walk, o trace é congelado **no ponto mais interno**, no `except` de
`LoxFunction.call`/`LoxClass.call`, antes do `finally` que desempilha: no topo os frames já
teriam sumido. `LoxRaise` também carrega o trace. No binário, o panic tira o retrato de
`lox_call_depth`/frames no instante do throw; uma exceção guarda `trace_depth` para o caso
de `try` sem handler (o `longjmp` desempilha, mas os frames continuam no array).

### 5. ABI do nativo

- `lox_stack_enter(name, file, decl_line, decl_column)` no prologue do chamado; o call
  site chega por três globais (`lox_call_file`, `lox_call_line`, `lox_call_column`)
  gravados pelo lowering **imediatamente antes** da chamada.
- `lox_call_site_restore()` devolve o call site do frame atual; usado no `ctor → init`
  depois dos inicializadores de campo.
- `LoxFrame { name, file, call_file, call_line, call_column }`; `file` alimenta o
  cabeçalho do panic (erro em módulo aponta o módulo), `call_*` alimenta o trace.
- `lox_panic` usa o arquivo do frame atual; `lox_panic_at` permite o R1015 usar a
  declaração do chamado. `LoxException` ganha `file` e `trace_depth`.
- `lox_call_depth` continua sendo o contrato do ADR-0077; o array tem
  `LOX_MAX_CALL_DEPTH` posições (≈320 KiB de BSS).

### 6. R1015 com posição

O [ADR-0077](0077-limite-de-pilha.md) decidiu "sem posição" por simetria e simplicidade.
Com os frames, a posição sai de graça: a ativação que estoura tem token de declaração nos
dois motores. O erro continua `R1015`, catchable e `exit 70`; muda apenas o cabeçalho
(`arquivo:linha:col`) e o trace. O ADR-0077 recebeu uma nota de atualização; o limite
10.000/64 MiB não mudou.

### 7. Limites declarados

- Exceção **capturada** não imprime trace e o valor `RuntimeError` não carrega frames;
  `raise;` reemite a partir do ponto do `raise` (o valor continua sem posição original).
- Um `try` sem handler preserva o trace do throw no binário (`trace_depth`) e no tree-walk
  (o mesmo objeto de erro); `raise` de um novo erro usa o novo ponto.
- `--error-format=short` não mostra frames (por definição de uma linha).
- Sem async: frames suspensos continuam fora (ADR-0037).

## Consequências

### Positivas

- Erro de runtime deixa de ser um ponto solto: mostra a cadeia e o call site de cada
  ativação, o que é a maior parte do custo de depurar.
- O binário e o interpretador continuam byte a byte iguais (I1), inclusive em módulos.
- O mesmo `Trace` serve para terminal, CI, JSON e, no futuro, LSP; sem segunda fonte de
  verdade.
- R1015 passa a ter posição sem mudar o contrato de pilha.
- A implementação é um array e três stores por chamada; não exige HIR/CFG nem shadow
  stack com `gc.statepoint`.

### Negativas / custos

- **Mudança de stderr**: todo erro de runtime não capturado ganha linhas `at ...`; golden
  cases, documentação e snapshots precisam refletir isso. É mudança de contrato pós-1.0,
  coberta pelo I1 no mesmo commit.
- Três stores + uma chamada com 4 argumentos por chamada Lox no binário; o bench nativo
  decide se precisa inlinar. O trace é só no erro, mas o call site é gravado sempre.
- O retrato do tree-walk exige um `except` extra nos dois `call`; custo desprezível no
  caminho feliz.
- `LoxException` cresce (arquivo e profundidade) e o `try` passa a copiar dois campos a
  mais.
- O nome do frame não é qualificado: dois métodos homônimos em classes diferentes
  aparecem iguais no trace (o call site desambigua).

### Neutras

- O formato humano do runtime continua sem trecho de código; o binário não embute a
  fonte.
- `trace` é campo aditivo do JSON v1 (`schema_version` não muda; consumidores que não
  conhecem o campo o ignoram).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só no tree-walk | Quebra o I1 em todo erro de runtime dentro de função; inaceitável. |
| Opt-in por flag/env | Esconde a feature e ainda exige o binário honrar o mesmo env; o default continuaria sem diagnóstico útil. |
| Só nome + declaração (sem call site) | Mais barato, mas não responde "quem chamou de onde"; o call site é o que localiza a causa. |
| Imprimir todos os 10.000 frames | stderr gigante e inútil; o recorte 5+5+elisão é determinístico e legível. |
| Shadow stack com `gc.statepoint` | Precisão que o produto não pede; projeto de semanas e acoplamento ao GC (ADR-0077 já rejeitou). |
| Frames como `notes` (texto livre) | Perde estrutura para JSON/LSP e obriga o consumidor a parsear. |
| HIR-lite para o trace | Não há controle de fluxo novo; um array de frames resolve. |
| Stack trace também em exceção capturada | O valor de exceção não carrega frames hoje; guardar 10k frames por `throw` custa memória e não tem consumidor. |

## Como verificar

- `tests/test_diagnostics.py` — `human`, `short`, JSON, elisão.
- `tests/test_modules.py` — erro de runtime em módulo aponta o módulo e o frame.
- `tests/cases/stack_trace*.lx` no `LEVELS` — diferencial nos três canais.
- `tests/test_backend.py -k stack` — R1015, reserva de pilha e o caso de módulo.
- `tests/test_determinism.py` — bytes idênticos entre seeds.
- `make check` e `make bench-native` (custo por chamada).

**Critério para revisitar:** o custo por chamada no bench; a necessidade de frames em
exceções capturadas; async (frames suspensos); LSP querendo mais estrutura (por exemplo,
`relatedInformation`).
