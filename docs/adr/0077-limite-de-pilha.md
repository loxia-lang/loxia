# ADR-0077 — Limite de profundidade de chamadas e `Stack overflow.`

- **Status:** proposed (decisão humana pendente; código não implementado)
- **Data:** 2026-11-15
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  [ADR-0031](0031-backend-nativo.md) (backend),
  [ADR-0042](0042-excecoes.md) e [ADR-0062](0062-l6-excecoes-unwinding.md)
  (exceções/unwinding), [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) (memória),
  [`../../TODO.md`](../../TODO.md) §3.1, [`../spec/garantias.md`](../spec/garantias.md)
- **Implementação:** nenhuma ainda; quando aceito, toca
  [`runtime/runtime.c`](../../runtime/runtime.c), [`src/backend/lower_functions.py`](../../src/backend/lower_functions.py),
  [`src/execution/interpreter.py`](../../src/execution/interpreter.py) e o corpus
  (`tests/cases/`)

## Contexto

Hoje a profundidade de chamadas não é contratada:

- o **tree-walk** usa a pilha do Python. Uma recursão Lox profunda vira
  `RecursionError` não tratado: traceback em stderr e **exit 1**, não um diagnóstico Lox;
- o **binário** usa a pilha C. Recursão profunda estoura a pilha e o processo morre com
  **SIGSEGV (139)**, sem mensagem e sem `exit 70`;
- [`garantias.md`](../spec/garantias.md) declara recursão profunda **fora do corpus**
  “até existir contador de pilha no runtime”. O I1, portanto, não cobre esse caso;
- o [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) cobre o **heap** (128 MiB, I1 até
  64 MiB vivos), mas não a pilha de chamadas.

Isso deixa um crash conhecido no MVP: um programa válido derruba o binário sem
diagnóstico. O contador é a menor intervenção que troca o crash por um erro Lox
determinístico e comparável entre os dois motores.

### Medições deste ambiente (2026-11-15)

Não são contrato; servem para dimensionar o limite. Python 3.13, pilha de 8 MiB,
`libgc` Boehm:

| Motor | Profundidade | Resultado |
| --- | --- | --- |
| tree-walk, `sys.setrecursionlimit` padrão (1000) | 120 | ok |
| tree-walk, limite padrão | 125 | `RecursionError`, exit 1 |
| tree-walk, `sys.setrecursionlimit(20000)` | 2.000 | ok |
| tree-walk, `sys.setrecursionlimit(20000)` | 5.000 | `RecursionError`, exit 1 |
| binário (`--emit=exe`) | 500.000 | ok |
| binário | 1.000.000 | SIGSEGV (139) |

O tree-walk é o gargalo. Um limite compartilhado precisa caber nele com margem, mesmo
depois de elevar o limite do Python.

## Decisão

### 1. Limite único e determinístico: 1.000 chamadas Lox

`LOX_MAX_CALL_DEPTH = 1000` é o mesmo número nos dois motores. Conta **chamadas Lox**
(função, método, lambda, construtor de classe), não primitivas nativas (`len`, `str`,
`math.*`, etc.). Código de topo e `main` ficam em profundidade 0.

A profundidade permitida é `0..999`; entrar na chamada de número 1000 é
`Stack overflow.`. O limite **não** é configurável por ambiente ou flag: mudar o número
é mudança de contrato (ADR novo + `garantias.md` + corpus).

### 2. O erro é `R1015`, capturável e sem posição na v1

- Mensagem: `Stack overflow.`
- Código novo: `R1015` (família runtime; não reutiliza código).
- `exit 70` quando não capturado.
- É `LoxRuntimeError`: `try`/`except LoxRuntimeError` captura e o programa continua.
- **Sem linha/coluna na v1**: o contador dispara na entrada da função, e a posição
  sintética (`line = 0`) produz `error[R1015]: Stack overflow.` nos dois motores. Um
  stack trace com frames é trabalho separado (TODO §3.1), não requisito deste ADR.

O formato exato é o que o renderizador já faz para posição sintética: sem
`arquivo:linha:col`. Isso mantém o I1 byte a byte sem inventar uma posição que um dos
motores não tem.

### 3. Tree-walk: contador no `call` e orçamento de recursão do Python

- `Interpreter` mantém `_call_depth` (inicia em 0).
- Em `visit_call_expr`, depois de calcular o callee e os argumentos e antes de
  `callee.call(...)`: se `_call_depth >= 1000`, levanta
  `LoxRuntimeError(token_sintético, "Stack overflow.", code=R1015)`; senão incrementa.
- `finally` decrementa em **todas** as saídas (retorno, `raise`, `ReturnSignal`).
- O CLI garante `sys.setrecursionlimit >= 20_000` antes de executar. Com 1.000 chamadas
  Lox e ~5–8 frames Python por chamada, sobram ~10× de margem para o pior caminho e para
  `try`/`finally` aninhados. O limite do Python não é contrato: é orçamento interno.
- Teste dedicado mede o caminho mais fundo (método + lambda + `try`) no limite.

### 4. Backend: contador no runtime e restauração no unwinding

- `runtime.c` ganha `lox_call_depth` e `lox_max_call_depth` (constante 1000), com:
  - `lox_stack_enter()`: se `depth >= 1000`, `lox_panic(0, 0, "R1015", "Stack overflow.")`;
    senão `depth += 1`;
  - `lox_stack_leave()`: `depth -= 1`.
- O lowering emite `lox_stack_enter()` na **entrada** de cada função/método/lambda/
  construtor gerado e `lox_stack_leave()` antes de cada `ret` normal. `main` e funções
  nativas não são instrumentadas.
- `LoxTryFrame` guarda a profundidade no `lox_try_push`. `lox_try_pop` restaura
  `lox_call_depth = frame->depth`, tanto no caminho normal quanto no `longjmp`; assim uma
  exceção que atravessa N funções não deixa o contador inflado.
- `raise`/`lox_panic` sem `try` continuam saindo por `exit 70`, sem precisar de
  `leave`.
- O `mod.verify()` continua sendo o gate do IR; a instrumentação não muda ABI de
  classes, closures ou containers.

### 5. Contrato e corpus

- `Stack overflow.` entra em `docs/spec/erros.md` (`R1015`) e em
  `docs/spec/garantias.md` (recursão deixa de ser “fora do corpus” no limite; abaixo de
  1.000 é suportada, acima é erro determinístico).
- Casos novos no corpus (nível `l4`, funções):
  - profundidade 999: roda e imprime o resultado;
  - profundidade 1.001: `error[R1015]: Stack overflow.`, `exit 70`, sem stdout;
  - `try`/`except LoxRuntimeError` em 1.001: captura, imprime e continua chamando
    funções (prova a restauração da profundidade);
  - `try`/`finally` durante a chamada que estoura: `finally` roda uma vez e o contador
    volta ao valor anterior.
- O teste diferencial compara stdout, stderr e exit code byte a byte, como sempre.

### 6. Fora de escopo

- Stack trace com `at f (linha N) ← main (linha M)`: depende de frames e posição de
  chamada; ADR/tooling separado.
- Limite configurável por `--max-depth` ou ambiente: quebra a ideia de contrato único e
  o I3.
- Detecção por guard page/`sigaltstack`/`SIGSEGV`: específico de plataforma e handler de
  sinal não é lugar para alocar/formatar com segurança.
- Contagem de primitivas nativas: não consomem pilha Lox recursiva; contá-las só
  criaria assimetria com o tree-walk.

## Consequências

### Positivas

- Recursão profunda deixa de ser SIGSEGV/traceback: vira erro Lox determinístico e
  capturável nos dois motores.
- O I1 ganha o caso de borda; o limite é observável e testado, não um detalhe de
  plataforma.
- O erro é recuperável: `try`/`except` pode continuar depois de um estouro.
- O custo no caminho de chamada é previsível (duas chamadas de runtime por chamada Lox).

### Negativas / custos

- **Mudança de comportamento**: programas que hoje recursam acima de 1.000 passam a
  falhar (o binário suportava ~500 mil; o tree-walk já falhava por volta de 120).
  Nenhum caso do corpus atual chega perto; a mudança precisa de nota no CHANGELOG.
- **Limite baixo para alguns algoritmos**: 1.000 é confortável para árvores/listas
  usuais, mas não para recursão linear em entradas grandes. Subir exige medir o
  tree-walk e novo ADR.
- Elevar `sys.setrecursionlimit` é global no processo do interpretador; o contador Lox
  é a proteção real, mas o orçamento precisa de teste para não mascarar `RecursionError`
  em caminhos internos.
- Duas chamadas a mais por chamada Lox no binário; medir em `make bench` e, se doer,
  inlinear o `load/add/store` no IR (sem mudar o contrato).
- O unwinding passa a depender de `lox_try_pop` restaurar a profundidade; um `try`
  esquecido no lowering vira contador inflado. O teste de `try`/`finally` é
  obrigatório.
- Erro sem linha/coluna na v1 é menos útil que um stack trace; é dívida declarada.

### Neutras

- O hard cap de heap (128 MiB) e o I1 até 64 MiB vivos não mudam; pilha e heap são
  orçamentos separados.
- O limite não depende de `--debug` nem de release/debug.
- O tree-walk e o binário continuam comparados pelo mesmo corpus; o caso de borda entra
  no nível `l4`.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só guarda no binário, tree-walk como está | Quebra o I1: um motor erra com `exit 70`, o outro com `RecursionError`/exit 1. |
| Deixar fora do corpus e não fazer nada | Mantém SIGSEGV e traceback; o MVP não pode prometer “memory safe” com crash conhecido. |
| Guard page + `sigaltstack`/`SIGSEGV` | Específico de plataforma; handler de sinal não pode alocar/formatar com segurança; `longjmp` do handler é frágil. |
| Limite 100 | Cabe no Python padrão sem elevar o limite, mas é baixo demais para recursão legítima (parsers, árvores). |
| Limite 10.000 | O tree-walk não chega lá nem com `setrecursionlimit(20000)` (5.000 já falha); exigiria pilha de thread maior e mais risco. |
| Limite configurável (`--max-depth`, env) | Contrato não determinístico e fácil de divergir entre motores; viola I3. |
| Shadow stack/`gc.statepoint` | Resolve stack trace preciso, mas é projeto de semanas e não é necessário para trocar o crash por erro. |
| Trampolim/VM com pilha explícita | Reescreve o tree-walk e o backend; o limite é uma guarda, não uma nova arquitetura. |

## Como verificar

Quando aceito e implementado:

- `tests/cases/stack_depth_ok.lox`: profundidade 999 termina com o resultado esperado.
- `tests/cases/stack_overflow.lox`: profundidade 1.001 termina em
  `error[R1015]: Stack overflow.`, `exit 70`, sem stdout; o teste diferencial exige
  igualdade byte a byte.
- Caso `try`/`except LoxRuntimeError`: captura, imprime e chama outra função depois;
  prova que `lox_try_pop` restaurou a profundidade.
- Caso `try`/`finally`: o `finally` roda uma vez, sem duplicar, e a profundidade volta.
- `tests/test_backend.py` cobre os casos no nível `l4`;
  `tests/test_determinism.py` continua verde.
- `make bench`: mede o custo por chamada em `recursion`/closures; se a regressão passar
  do limite acordado, inlinear o contador antes de fechar.
- `make check` verde e `docs/spec/garantias.md` atualizado.

**Critério para revisitar:** 1.000 insuficiente para programas reais; custo de chamada
inaceitável; necessidade de stack trace com frames; diferença de pilha entre plataformas
que faça 1.000 não ser seguro. Nesses casos, ADR novo — não ajuste silencioso do número.

## Referências

- [ADR-0014](0014-identidade-e-invariantes.md) — I1–I4 e portão de admissão.
- [ADR-0031](0031-backend-nativo.md) — backend e decisão 7.
- [ADR-0042](0042-excecoes.md) e [ADR-0062](0062-l6-excecoes-unwinding.md) — exceções e
  `setjmp`/`longjmp`.
- [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) — heap e orçamento de memória.
- [`../spec/garantias.md`](../spec/garantias.md) — o que a linguagem promete hoje.
- [`../../TODO.md`](../../TODO.md) §3.1 — stack trace de runtime.
