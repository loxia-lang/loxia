# ADR-0077 — Limite de profundidade de chamadas e `Stack overflow.`

> **Atualizado por** [ADR-0078](0078-nome-loxia-extensao-lx.md): a classe embutida
> `LoxRuntimeError` passou a se chamar `RuntimeError`. **Revisado em 2026-11-15** para o
> contrato de 10.000 chamadas / 64 MiB; a medição original confundia o limite de frames
> do Python com a pilha C (ver §"Medições").
>
> **Atualizado por** [ADR-0089](0089-stack-trace-de-runtime.md): `R1015` ganhou a posição
> da declaração do chamado e todo erro de runtime não capturado imprime stack trace. O
> limite 10.000/64 MiB e o caráter catchable **não** mudaram; só a ABI de
> `lox_stack_enter` (agora com nome, arquivo e posição) e o cabeçalho do erro.

- **Status:** accepted (implementado)
- **Data:** 2026-11-15
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  [ADR-0031](0031-backend-nativo.md) (backend),
  [ADR-0042](0042-excecoes.md) e [ADR-0062](0062-l6-excecoes-unwinding.md)
  (exceções/unwinding), [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) e
  [ADR-0087](0087-heap-cap-e-self-hosting.md) (memória), [`../../TODO.md`](../../TODO.md)
  §3.1, [`../spec/garantias.md`](../spec/garantias.md)
- **Implementação:** [`runtime/core.c`](../../runtime/core.c),
  [`loxia_core/backend/lower_functions.py`](../../loxia_core/backend/lower_functions.py),
  [`loxia_core/backend/lower_class_codegen.py`](../../loxia_core/backend/lower_class_codegen.py),
  [`loxia_core/backend/lower.py`](../../loxia_core/backend/lower.py),
  [`loxia_core/execution/lox_function.py`](../../loxia_core/execution/lox_function.py),
  [`loxia_core/execution/lox_class.py`](../../loxia_core/execution/lox_class.py),
  [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py),
  [`loxia_core/execution/limits.py`](../../loxia_core/execution/limits.py),
  [`loxia_core/backend/driver.py`](../../loxia_core/backend/driver.py) e o corpus (`tests/cases/`)

## Contexto

Antes deste ADR a profundidade de chamadas não era contratada:

- o **tree-walk** usava a pilha do Python sem contador Lox; recursão profunda virava
  `RecursionError` não tratado (traceback em stderr, **exit 1**);
- o **binário** usava a pilha C; recursão profunda morria com **SIGSEGV (139)**, sem
  mensagem e sem `exit 70`;
- [`garantias.md`](../spec/garantias.md) declarava recursão profunda **fora do corpus**;
- o [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) cobre o **heap**, não a pilha.

O contador é a menor intervenção que troca o crash por um erro Lox determinístico,
capturável e comparável entre os dois motores.

### Medições deste ambiente (2026-11-15)

Python 3.13, pilha C de 8 MiB, `libgc` Boehm. Números de engenharia, não contrato:

| Motor | Profundidade | Resultado |
| --- | --- | --- |
| tree-walk, `sys.setrecursionlimit` default (1000) | ~100 | `RecursionError`, exit 1 |
| tree-walk, limite proporcional (200k) | 10.000 | ok (~50 MB RSS no pior caminho) |
| tree-walk, limite proporcional (15M) | 1.000.000 | ok, **~2,2 GB RSS e 7 s** |
| binário, função simples | 500.000 | ok com 8 MiB |
| binário, função simples | 1.000.000 | SIGSEGV com 8 MiB; ok com 64 MiB |
| binário, função com 200 locais | 10.000 | SIGSEGV com 8 MiB; ok com 64 MiB |

A medição antiga (“5.000 falha com `setrecursionlimit(20000)`”) era o **limite de frames
do Python**, não a pilha C: cada chamada Lox consome ~11–13 frames Python. Com orçamento
proporcional, o tree-walk chega a 1M — o limite real é memória (~2,2 KB/chamada), não C
stack. O binário gasta ~16 B a ~1,2 KB por frame, dependendo do corpo.

## Decisão

### 1. Limite único e determinístico: 10.000 chamadas Lox

`LOX_MAX_CALL_DEPTH = 10_000` é o mesmo número nos dois motores (`loxia_core/execution/limits.py`
e `-D` do driver para o runtime). A profundidade permitida é `1..10_000`; a chamada
10.001 é `Stack overflow.`. Código de topo e `main` ficam em profundidade 0.

Conta **ativações Lox**: função, método, lambda, `init` e construtor de classe. Chamadas
nativas (`len`, `str`, `math.*`, construtor de `Exception`/`RuntimeError`) **não** contam.
Construtor + `init` contam **duas** ativações, porque são dois frames reais nos dois
motores. O limite não é configurável por ambiente ou flag; mudar o número é mudança de
contrato (ADR novo + `garantias.md` + corpus).

### 2. O erro é `R1015`, capturável e sem posição

- Mensagem: `Stack overflow.`
- Código: `R1015`, família runtime (`loxia_core/diagnostics/codes.py`).
- `exit 70` quando não capturado; `try`/`except RuntimeError` captura e o programa
  continua.
- **Sem linha/coluna**: o contador dispara na entrada da função; o token sintético tem
  `line = 0` e o renderizador imprime `error[R1015]: Stack overflow.` sem localização.
  Stack trace com frames continua trabalho separado (TODO §3.1).
- O formato é idêntico ao `lox_panic(0, 0, "R1015", ...)` do binário, preservando o I1.

> **Nota (ADR-0089, 2026-11-15):** os dois bullets acima foram revisados. `R1015` agora
> aponta a declaração do chamado e traz o trace; o formato continua idêntico nos dois
> motores. O restante desta decisão (limite, contagem de ativações, unwinding) vale.

### 3. Tree-walk: contador nas ativações e orçamento de recursão do Python

- `Interpreter` mantém `_call_depth`, zerado no início de cada `interpret`.
- `_enter_call()`: se `_call_depth >= 10_000`, levanta
  `LoxRuntimeError(token_sintético, "Stack overflow.", code=R1015)`; senão incrementa.
- `_leave_call()` no `finally` de `LoxFunction.call` e `LoxClass.call`, cobrindo retorno
  normal, `raise` e `ReturnSignal`.
- O interpretador eleva `sys.setrecursionlimit` para **200.000** (≈15 × 10.000 + folga)
  em `ensure_recursion_budget()`. Esse limite é orçamento interno, não contrato: o teto
  observável é `MAX_CALL_DEPTH`.
- Construtor de exceção embutida usa `LoxExceptionClass.call`, que não conta — espelhando
  o ctor sintético não instrumentado do backend.

### 4. Backend: contador no runtime e restauração no unwinding

- `runtime/core.c` ganha `lox_call_depth` e:
  - `lox_stack_enter()`: se `depth >= LOX_MAX_CALL_DEPTH`,
    `lox_panic(0, 0, "R1015", "Stack overflow.")`; senão `depth += 1`;
  - `lox_stack_leave()`: `depth -= 1`.
- O lowering emite `lox_stack_enter()` na **entrada** de cada função/método/lambda/`init`
  gerado e no ctor de classe do usuário; `lox_stack_leave()` antes de cada `ret` normal.
  `main`, thunks de método/interface, funções nativas e o ctor sintético de
  `Exception`/`RuntimeError` **não** são instrumentados.
- Todo `ret` de função de usuário passa por `_stack_leave()`: retorno explícito em
  [`lower.py`](../../loxia_core/backend/lower.py), retorno implícito em
  [`lower_functions.py`](../../loxia_core/backend/lower_functions.py) e ctor em
  [`lower_class_codegen.py`](../../loxia_core/backend/lower_class_codegen.py).
- `LoxTryFrame` guarda `depth` no `lox_try_push`; `lox_try_pop` restaura
  `lox_call_depth = frame->depth` no caminho normal e após `longjmp`. Uma exceção que
  atravessa N funções não deixa o contador inflado.
- `raise`/`lox_panic` sem `try` continuam saindo por `exit 70`, sem precisar de `leave`.
- `mod.verify()` continua sendo o gate do IR; a instrumentação não muda ABI de classes,
  closures ou containers.

### 5. Orçamento de pilha e reserva do SO

- O contrato declara **64 MiB** de orçamento de pilha (`STACK_BUDGET_BYTES` em
  `limits.py`). O binário reserva **128 MiB** de soft limit via `setrlimit(RLIMIT_STACK)`
  em `lox_init` (clampado ao hard), antes de qualquer recursão. A reserva é virtual e
  commit sob demanda; o GC continua enxergando só a faixa usada.
- Em plataformas com hard limit menor (ex.: 64 MiB no macOS), o clamp usa o hard
  disponível; 10.000 chamadas com frames usuais cabem com margem. Frame patológico acima
  do orçamento é dívida declarada; uma guarda por SP fica como follow-up se doer.
- O interpretador não precisa de reserva de thread: com Python 3.13 as chamadas
  Python→Python não empilham C stack; 10.000 chamadas cabem nos 8 MiB default (medido).

### 6. Contrato e corpus

- `Stack overflow.` entra em `docs/spec/erros.md` (`R1015`) e em
  `docs/spec/garantias.md`: até 10.000 chamadas (e dentro do orçamento de 64 MiB) é
  suportado; acima é erro determinístico.
- Casos novos em `tests/cases/` e no manifesto:
  - `stack_depth_ok.lx` (10.000 chamadas) roda;
  - `stack_overflow.lx` (10.001) → `error[R1015]: Stack overflow.`, exit 70, sem stdout;
  - `stack_overflow_caught.lx` captura, imprime e continua chamando funções;
  - `stack_overflow_finally.lx` prova `finally` uma vez e restauração da profundidade;
  - `stack_methods.lx` e `stack_ctor.lx` cobrem método e ctor+init;
  - `stack_exception.lx` prova que o ctor de exceção embutida não conta;
  - `stack_exception_user.lx` prova que R1015 atravessa um `try` com handler que não
    casa e chega ao topo como R1015 (não R1010).
- O teste diferencial compara stdout, stderr e exit code byte a byte.
- `tests/test_backend.py` cobre o frame gordo com soft limit de 8 MiB, provando a reserva
  de `lox_init`.

## Consequências

### Positivas

- Recursão profunda deixa de ser SIGSEGV/traceback: vira erro Lox determinístico e
  capturável nos dois motores.
- O I1 ganha o caso de borda; o limite é observável e testado, não um detalhe de
  plataforma.
- O erro é recuperável: `try`/`except` pode continuar depois de um estouro.
- O custo no caminho de chamada é previsível (duas chamadas de runtime por chamada Lox);
  se o bench acusar regressão, o contador pode ser inlinado no IR sem mudar o contrato.

### Negativas / custos

- **Mudança de comportamento**: programas acima de 10.000 chamadas passam a falhar com
  R1015 (o binário suportava ~500 mil; o tree-walk falhava antes por volta de 100 sem o
  orçamento). Nenhum caso do corpus chega perto; o CHANGELOG registra.
- **Limite ainda finito**: 10.000 é confortável para árvores/listas usuais, mas não para
  recursão linear em entradas gigantes. Subir exige medir o tree-walk e novo ADR; 1M custa
  ~2,2 GB no oráculo.
- Elevar `sys.setrecursionlimit` é global no processo; o contador Lox é a proteção real.
- Duas chamadas a mais por chamada Lox no binário; medir em `make bench-native`.
- O unwinding depende de `lox_try_pop` restaurar a profundidade; um `try` esquecido no
  lowering vira contador inflado. Os testes de `try`/`finally` policiam.
- Erro sem linha/coluna é menos útil que um stack trace; dívida declarada.

### Neutras

- O hard cap de heap (512 MiB, [ADR-0087](0087-heap-cap-e-self-hosting.md)) e o I1 até
  64 MiB vivos são orçamentos separados; não mudam com a pilha.
- O limite não depende de `--debug` nem de release/debug.
- O tree-walk e o binário continuam comparados pelo mesmo corpus.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só guarda no binário, tree-walk como está | Quebra o I1: um motor erra com `exit 70`, o outro com `RecursionError`/exit 1. |
| Deixar fora do corpus e não fazer nada | Mantém SIGSEGV e traceback; o MVP não pode prometer “memory safe” com crash conhecido. |
| Guard page + `sigaltstack`/`SIGSEGV` | Específico de plataforma; handler de sinal não pode alocar/formatar com segurança; `longjmp` do handler é frágil. |
| Limite 1.000 | Seguro, mas baixo demais para recursão legítima; foi o número original, revisado aqui. |
| Limite 100.000 ou 1M | O tree-walk custa ~2,2 KB/chamada; 1M = ~2,2 GB e 7 s no oráculo. 100k é possível, mas o teste de borda fica pesado e o default deixa de ser econômico. |
| Limite configurável (`--max-depth`, env) | Contrato não determinístico e fácil de divergir entre motores; viola I3. |
| Shadow stack/`gc.statepoint` | Resolve stack trace preciso, mas é projeto de semanas e não é necessário para trocar o crash por erro. |
| Trampolim/VM com pilha explícita | Reescreve o tree-walk e o backend; o limite é uma guarda, não uma nova arquitetura. |
| Pilha crescente (Go-style/segmentos) | Exige GC escanear todos os segmentos e unwinding entre eles; projeto à parte, sem dor demonstrada. |

## Como verificar

- `uv run pytest -m backend -k stack` cobre os casos e o teste diferencial.
- `uv run python -m tests.runner stack` cobre os goldens.
- `uv run pytest -m backend -k stack_reserve` prova a reserva com soft limit de 8 MiB.
- `make bench-native`: mede o custo por chamada; se a regressão passar do limite acordado,
  inlinar o contador antes de fechar.
- `make check` verde e `docs/spec/garantias.md` atualizado.

**Critério para revisitar:** 10.000 insuficiente para programas reais; custo de chamada
inaceitável; necessidade de stack trace com frames; ou dor real de frame gordo acima do
orçamento de 64 MiB. Nesses casos, ADR novo — não ajuste silencioso do número.

## Referências

- [ADR-0014](0014-identidade-e-invariantes.md) — I1–I4 e portão de admissão.
- [ADR-0031](0031-backend-nativo.md) — backend e decisão 7.
- [ADR-0042](0042-excecoes.md) e [ADR-0062](0062-l6-excecoes-unwinding.md) — exceções e
  `setjmp`/`longjmp`.
- [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) e
  [ADR-0087](0087-heap-cap-e-self-hosting.md) — heap e orçamento de memória.
- [`../spec/garantias.md`](../spec/garantias.md) — o que a linguagem promete hoje.
- [`../../TODO.md`](../../TODO.md) §3.1 — stack trace de runtime.
