# ADR-0095 — Processos, streams e `poll` no kernel (`std.proc`)

- **Status:** accepted (implementado)
- **Data:** 2026-11-16
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0071](0071-primitivas-de-runtime.md) (tabela única, `ambient`),
  [ADR-0072](0072-stdlib-batteries.md) (batteries), [ADR-0094](0094-kernel-io-flush-e-read-utf8.md)
  (stdio por bytes), [ADR-0037](0037-async-direcao.md) (async **não** é isto),
  [`../../IDEIAS.md`](../../IDEIAS.md) I-11, [`../../TODO.md`](../../TODO.md) §13.9
- **Implementação:** `loxia_core/execution/primitives.py`,
  `loxia_core/execution/proc_runtime.py`, `runtime/proc.c`, `std/proc.lx`,
  `runtime/kernel_gen.h`, `tests/test_proc.py`, `tests/test_backend.py`

## Contexto

O [ADR-0094](0094-kernel-io-flush-e-read-utf8.md) fechou o stdio por bytes (flush +
`readUtf8`), que é o que um protocolo por stdio exige. Faltava o outro lado do
ferramental: **rodar um programa** e falar com ele — para o `loxia fmt`/`loxia test`, para
delegar diagnóstico ao CLI (caminho B do LSP) e para qualquer script que orquestra
comandos.

O [I-11](../../IDEIAS.md) propunha handles opacos (`Process`/`Stream`) como tipos novos.
Isso exigiria `ValueType`/`Ty`/lowering próprios e uma ABI nova — trabalho de linguagem,
não de stdlib. A alternativa escolhida usa o que já existe: **handle é `Int`** (id na
tabela do kernel) e as classes de conveniência (`Process`, `Stream`, `Output`) são Lox
normal em `std/proc.lx`. O dia em que houver tipo opaco, a casca muda sem mudar o
usuário.

## Decisão

### 1. Namespace `process` no kernel, `std.proc` na stdlib

As primitivas são `process.*` (baixo nível, handles `Int`); a API ergonômica é o módulo
`std.proc` (`p.run`, `p.spawn`). Nomes distintos de propósito: `import std.proc as p`
não sombreia o namespace do kernel, e `process` é um nome improvável de colidir com a
casca. Nada de shell: `argv` é lista e o executável é achado por `posix_spawnp` (PATH).

### 2. Handles e recursos

- Ids **1-based** numa tabela fixa (`LOX_MAX_PROC_HANDLES = 256`); `0` nunca é válido e
  `process.spawn` devolve `0` quando não conseguiu criar o processo.
- Cada processo tem três streams (stdin/stdout/stderr) em pipes, obtidos por
  `process.stdin/stdout/stderr(id)`.
- `close(id)` libera o slot e fecha os descritores; **não mata** um processo em execução.
  Depois de fechar, o id é inválido (`R1000: process: invalid handle.`).
- `wait(id)` colhe o filho e guarda o status (idempotente); devolve o código ou
  `-sinal` quando o filho morre por sinal. `kill(id)` manda `SIGKILL` e devolve `false`
  se o processo já saiu.
- `SIGPIPE` é ignorado no `lox_init`: escrever num pipe fechado devolve `false`, não mata
  o processo.

### 3. Leitura por bytes em fronteira de UTF-8

`process.read(id, n)` devolve **até** `n` bytes, nunca no meio de um caractere: a
sequência incompleta no fim fica guardada no handle para a próxima chamada. Se o stream
terminar no meio de uma sequência, é erro; bytes que não são UTF-8 estrito também
(`R1000: process.read() expects UTF-8 input.`). Sem isso, qualquer saída maior que o
buffer cortaria um caractere multi-byte e o erro apareceria como se o filho tivesse
emitido lixo.

### 4. `poll` é a concorrência (não é async)

`process.poll(ids, timeout_ms) -> List[Int]` aceita streams e processos misturados:

- stream: pronto quando há bytes ou EOF;
- processo: pronto quando já saiu (colhe com `WNOHANG` e guarda o status);
- `timeout_ms < 0` = infinito, `0` = não bloqueante, `> 0` = limite em ms;
- devolve os ids na ordem da entrada, sem duplicatas; lista vazia = timeout.

`poll` **não** é `async` ([ADR-0037](0037-async-direcao.md)): async exige frames
materializáveis e um scheduler; `poll` é I/O não bloqueante com um único fluxo de
controle. Também não há thread: o `std.proc.run` usa `poll` para drenar stdout e stderr
sem deadlock.

### 5. `std.proc`

- `class Stream`: `read(n) -> String?`, `write(text) -> Bool`, `close()`.
- `class Process`: `id`, `stdin`/`stdout`/`stderr`, `wait() -> Int`, `kill() -> Bool`,
  `close()`.
- `class Output`: `code`, `stdout`, `stderr`.
- `fn spawn(argv: List[String]) -> Process?`.
- `fn run(argv, stdin = "", timeoutMs = 0) -> Output?`: escreve `stdin` (antes do
  primeiro `poll`), fecha o canal, drena stdout/stderr com `poll` até EOF, chama `wait` e
  devolve `Output`. `timeoutMs > 0` mata o processo e devolve `nil`. `nil` também quando
  `spawn` falha.

O limite prático de `stdin` é o buffer do pipe (`~64 KiB` no Linux): texto maior pode
bloquear se o filho não ler. Documentado, não resolvido (resolver exige poll de escrita).

### 6. Escopo

Tudo é `ambient: true` e POSIX (`posix_spawnp`/`poll`/`waitpid`): fora do corpus I1/I3,
sem Windows por enquanto. Os testes usam o próprio `sys.executable` como filho, sem
depender de `cat`/shell.

## Consequências

### Positivas

- O ferramental de processo existe: rodar formatter/test runner, delegar `check --json`,
  orquestrar comandos, capturar saída e código, com timeout.
- Sem shell: nada de interpolar string em comando; sem quoting, sem injeção.
- A casca é Lox compilado como qualquer código — o backend não ganhou ABI nova, e o
  dogfooding (`run` usa `poll` e concatenação) exercita o L6.
- `poll` resolve I/O concorrente sem thread nem `async`, e é reutilizável para rede
  (I-11) mais tarde.

### Negativas / custos

- Kernel 19 → **29** primitivas: chegou ao orçamento de ~30 do I-11. O próximo
  crescimento deve vir com tipos opacos (ou pergunta séria sobre a camada).
- Handles são `Int`: não há proteção estática contra passar o id errado. A validação é
  em runtime, com a posição da chamada (`site`).
- Limite de 64 KiB de stdin no `run`; `read(n)` pode devolver `""` para `n` minúsculo no
  meio de um caractere multi-byte (callers usam blocos).
- POSIX-only; Windows fica fora até haver um shim próprio.
- Encerrar processos por `close` é explícito: quem esquece o `close` deixa descritor
  aberto (não há finalizer; Boehm não é determinístico).
- `run` é Lox, então uma saída enorme paga `List[String]` + `join` (O(n) no total, mas com
  alocações por bloco de 4 KiB).

### Neutras

- Nenhuma sintaxe nova (gate do [ADR-0066](0066-orcamento-e-gate-sintatico.md)).
- Nenhum byte de programa gerado muda: as primitivas novas só entram quando chamadas.
- `std.proc` estreia a classe `Output`; não é um tipo novo de linguagem.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `HandleTy` opaco já | Exige `ValueType`/`Ty`/lowering/ABI novos; o wrapper em Lox entrega o mesmo produto agora e pode ser trocado depois sem mudar a API. |
| `proc` como nome do namespace do kernel | `import std.proc as proc` sombrearia o kernel dentro de `std.proc`; o nome `process` evita a colisão. |
| `sh -c "cmd"` | Volta quoting/injeção e viola "nada implicitamente"; argv é lista. |
| Threads | Modelo de memória, GC e data races; `poll` cobre o caso de I/O. |
| `async`/`await` para isso | Precisa de frames materializáveis (ADR-0037) e não é pré-requisito para rodar comandos. |
| `run` em C | O kernel deve ser syscall; a orquestração (drenar, concatenar, timeout) é lógica e fica em Lox. |
| `readLine` em vez de `read(n)` | Linha perde bytes exatos e trava em prompt sem `\n`; `read(n)` com fronteira de UTF-8 preserva o stream. |
| Handles em `Any` | Perde a checagem e o backend teria um tag novo; `Int` + validação é o menor passo. |

## Como verificar

- `uv run pytest tests/test_proc.py` — `run` (stdout, stderr, código, 3.000 code points
  acima do chunk de 4 KiB, timeout mata), `spawn`/`poll`/`wait`, handle de tipo errado com
  posição.
- `uv run pytest tests/test_backend.py -k "proc or process_spawn"` — diferencial
  byte a byte entre tree-walk e binário, inclusive os 6.000 bytes de `ç`.
- `uv run pytest tests/test_primitives.py tests/test_primitives_gen.py` — tabela e ABI
  gerada (`kernel_gen.h`).
- **Critério para revisitar:** kernel acima de ~30 primitivas, necessidade de Windows, ou
  um consumidor que precise de `poll` de escrita/streams não bloqueantes → aí a conversa
  é tipo opaco + event loop, não mais primitiva solta.

## Referências

- `posix_spawn(3)`, `poll(2)`, `waitpid(2)` — POSIX.
- [`../../IDEIAS.md`](../../IDEIAS.md) I-11 — catálogo de capacidades de host.
- [`../../TODO.md`](../../TODO.md) §13.9 — fila e orçamento do kernel.
- [`../spec/semantica.md`](../spec/semantica.md) — `std.proc` e `process.*`.
