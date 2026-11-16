# ADR-0094 — Kernel: `io.flush` e `io.readUtf8` (stdio orientado a bytes)

- **Status:** accepted (implementado)
- **Data:** 2026-11-16
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0071](0071-primitivas-de-runtime.md) (tabela única, `ambient`),
  [ADR-0072](0072-stdlib-batteries.md) (política de batteries),
  [ADR-0079](0079-stdlib-t2.md) (T2), [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (LSP é
  stdio, não rede), [`../../TODO.md`](../../TODO.md) §9.1 (`R1`) e §13.9,
  [`../../IDEIAS.md`](../../IDEIAS.md) I-11
- **Implementação:** `loxia_core/execution/primitives.py`,
  `loxia_core/backend/lower_calls.py`, `runtime/kernel.c`,
  `tests/test_kernel.py`, `tests/test_backend.py`,
  `tests/cases/kernel_io.lx`, [`../spec/semantica.md`](../spec/semantica.md) e
  [`../spec/garantias.md`](../spec/garantias.md)

## Contexto

O kernel tinha 17 primitivas ([ADR-0071](0071-primitivas-de-runtime.md)) e duas lacunas
apareceram ao avaliar protocolo por stdio (LSP/MCP/JSONL):

1. **`io.write` não fazia flush no binário** (o oráculo fazia). O I1 compara os bytes do
   processo inteiro, então o `exit` escondia a diferença: os bytes finais eram iguais e só
   o *momento* divergia. Consequências reais: `std.io.prompt` nunca mostrava a mensagem no
   binário (tty é line-buffered e `io.write` sem `\n` ficava no buffer) e qualquer
   consumidor de stdout em pipe travava ao encher o buffer do stdio.
2. **Não havia leitura orientada a bytes.** `io.readLine`/`io.readAll` são de texto e não
   servem para framing `Content-Length`, que conta **bytes** UTF-8.

O [ADR-0071](0071-primitivas-de-runtime.md) exige ADR para crescer o kernel; este é o
crescimento 18–19.

## Decisão

### 1. Flush é contrato de `io.write`/`io.writeErr`

- `lox_io_write`/`lox_io_write_err` fazem `fflush` no canal depois do `fwrite`; o oráculo
  já fazia `flush()` por chamada.
- Nova primitiva `io.flush() -> Nil`, idempotente, que força stdout **e** stderr.
- `print` continua com o buffer do stdio (bloco em pipe, linha em tty) nos dois motores:
  é simétrico e não entra neste contrato. Uniformizar (flush por `print`) fica em aberto;
  exige medir o custo em laço com `print`.
- Efeito colateral desejado: `std.io.prompt` volta a funcionar no binário e o mesmo
  `io.write` serve a um protocolo por stdio.

### 2. `io.readUtf8(n) -> String?`

Semântica fechada (oráculo e binário):

| Caso | Resultado |
| --- | --- |
| `n < 0` | `RuntimeError` (`R1000`) `io.readUtf8() expects a non-negative count.` |
| `n == 0` | `""`, sem tocar no stdin |
| exatamente `n` bytes válidos | `String` decodificada |
| EOF imediato (0 bytes) | `nil` |
| EOF no meio (menos de `n`) | `RuntimeError` `io.readUtf8() expects exactly N bytes.` |
| bytes que não são UTF-8 estrito | `RuntimeError` `io.readUtf8() expects UTF-8 input.` |

UTF-8 estrito = rejeita overlong, surrogates, `> U+10FFFF` e sequência truncada; espelha
`bytes.decode("utf-8")`. A primitiva é `ambient: true` (fora do corpus I1/I3), mas os
erros são determinísticos e ganham teste diferencial com stdin fixo.

**Mistura de leituras:** `io.readUtf8` lê do buffer binário; `io.readLine`/`io.readAll`
usam a camada de texto. No interpretador, o `TextIOWrapper` faz readahead, então misturar
os dois no mesmo stdin é indefinido (no binário é seguro, porque o `FILE*` é único). Está
documentado na spec; não é bug a corrigir agora.

### 3. `site: bool` na tabela de primitivas

Primitivas que podem falhar passaram a declarar `site = True`: o lowering acrescenta
`(line, column)` do `(` da chamada aos argumentos do símbolo C, e o panic usa essa posição.
Isso fecha a lacuna de diagnóstico do `io.readUtf8` (o oráculo sempre teve a posição) e
prepara `proc`/`net` ([I-11](../../IDEIAS.md)). Primitivas antigas continuam sem `site`
enquanto não forem migradas (`R2` no TODO §9.1).

## Consequências

### Positivas

- Protocolo por stdio passa a ser possível em Loxia: framing por bytes + saída sem
  deadlock.
- O contrato de streaming fica explícito e policiado por um teste que distingue "flushou"
  de "flushou no exit" — o runner antigo não conseguia.
- `io.readUtf8` tem paridade exata de mensagem, código e posição entre os dois motores,
  incluindo os bytes inválidos.
- `site` é reutilizável: a próxima primitiva falível não precisa de caso especial no
  lowering.

### Negativas / custos

- Duas superfícies novas de linguagem (`io.flush`, `io.readUtf8`) — spec, checker (via
  tabela), docs de builtin e golden no mesmo commit.
- `fflush` por `io.write` custa uma syscall a mais; `io.write` não é caminho quente, mas
  fica registrado como medição pendente se algum benchmark reclamar.
- `io.readUtf8` exige `sys.stdin.buffer` no oráculo; stdin que não é binário (ex.:
  `StringIO` em teste) dá erro explícito.
- Misturar leitura de texto e de bytes é indefinido no interpretador (assimetria com o
  binário, documentada).
- O kernel foi de 17 para 19 primitivas; o teto novo precisa de justificativa a cada
  crescimento ([I-11](../../IDEIAS.md) sugere ~30 como sinal de camada errada).

### Neutras

- `io.readUtf8` é `ambient`, então não entra no corpus I1/I3; `io.flush` é determinístico
  e entra (o caso `kernel_io.lx` passou a chamá-lo).
- Nenhuma sintaxe nova: nada de gate do [ADR-0066](0066-orcamento-e-gate-sintatico.md).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Bufferizar os dois motores e só flushar em `exit`/`io.flush` | Mudaria a semântica atual de `io.write` no oráculo e exigiria reimplementar buffering em Python; o problema real (prompt/protocolo) continua sem flush no momento certo. |
| Fazer `print` também flushar | Simétrico hoje; sem medição do custo em laço com `print`. Fica em aberto. |
| `io.readBytes(n) -> Bytes` | Não existe tipo `Bytes`; `readUtf8` resolve framing de protocolo de texto sem abrir a representação binária ([I-11](../../IDEIAS.md)). |
| `io.readUtf8` sem `site`, com panic em `0:0` | Perderia a posição que o oráculo já tem e a mensagem sairia sem `arquivo:linha:col`. |
| Reusar `io.readAll` + fatiar no Lox | `readAll` bloqueia até EOF e não permite framing incremental. |
| `readUtf8` devolver parcial no EOF | Esconderia truncamento de protocolo; erro é o contrato correto. |

## Como verificar

- `uv run pytest tests/test_kernel.py -k utf8` — semântica do oráculo (exato, `0`,
  multibyte, truncado, inválido).
- `uv run pytest tests/test_backend.py -k "read_utf8 or flush_antes"` — paridade
  byte a byte (stdout, stderr e exit code) e o teste de streaming nos dois motores.
- `uv run pytest tests/test_backend.py -k kernel` — `kernel_io.lx` com `io.flush` no
  corpus.
- **Critério para reverter:** se o flush por escrita regredir um benchmark de forma
  perceptível, reabrir com a opção "buffer + `io.flush` explícito nos dois motores" e
  medir; se `site` se mostrar inútil, removê-lo antes de `proc`/`net`.

## Referências

- LSP 3.17 — framing `Content-Length`:
  <https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/>
- JSON-RPC 2.0 — <https://www.jsonrpc.org/specification>
- [`../../TODO.md`](../../TODO.md) §9.1 (`R1`, `R2`) e §13.9 (capacidades de host)
- [`../../IDEIAS.md`](../../IDEIAS.md) I-11 (por que rede não era o problema do LSP)
