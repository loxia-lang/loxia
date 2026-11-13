# ADR-0037 — Async: colored, determinístico e pós-M7

- **Status:** accepted (direção; implementação pendente)
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (I1–I3 e portão),
  [ADR-0026](0026-freeze-1.0.md) (freeze), [ADR-0031](0031-backend-nativo.md) (frames,
  GC, backend), [ADR-0010](0010-tipagem-estatica.md) (checker),
  [ADR-0016](0016-api-stdlib-hibrida.md) (namespaces nativos),
  [ADR-0021](0021-tipos-de-funcao.md) (`FnTy`), [ADR-0027](0027-generics-t3b.md)
  (genericidade), [`../spec/garantias.md`](../spec/garantias.md), [`../../TODO.md`](../../TODO.md)
  §9, [`../../IDEIAS.md`](../../IDEIAS.md) I-7 (paralelismo)
- **Implementação:** parcial. `async`/`await` já estão reservadas em
  `src/frontend/keywords.py` (sem sintaxe); `Task`, checker e runtime ainda não existem.
  Nenhum programa do corpus usava esses nomes.

## Contexto

O objetivo é ter assincronismo "de preferência real" em algum momento. Hoje a linguagem
1.0 está congelada, não tem I/O (só `print`), não tem módulos, e async está listado como
**fora** em [`TODO.md`](../../TODO.md) §8 e [`ESCOPO.md`](../../ESCOPO.md). Sem uma direção
registrada, a primeira implementação decidiria no calor do código — e as decisões caras
(frames, GC, ABI) seriam tomadas antes do L4/L6, que é onde elas realmente importam.

Restrições que qualquer desenho precisa respeitar:

- **I1** — o tree-walk é o oráculo; o compilado reproduz stdout/stderr/exit code.
- **I2** — nada implícito: sem espera invisível, sem assimilação de thenable.
- **I3** — determinismo observável; sem endereço, PID, timestamp ou ordem de hash.
- O backend emite `.o` com o LLVM embutido do `llvmlite` (22.1.0) e linka com `cc`; o
  `NewPassManager` do `llvmlite` 0.50 não expõe `coro-split` nem pipeline textual
  ([ADR-0031](0031-backend-nativo.md)).
- Memória é arena com `lox_alloc`; Boehm é a direção preferida (ADR-0031 §7).

A pergunta que dominou a discussão: **async colore tudo?** Sim, e não há como evitar de
graça. Suspender no meio de uma chamada exige preservar a pilha (*stackful*) ou transformar
o programa em máquina de estados em todo ponto de chamada (*stackless*). A primeira empurra
a complexidade para o runtime; a segunda, para o código-fonte (as cores). Este ADR escolhe a
segunda e compra de volta o topo: **o topo do script pode `await`**, então não existe
`async fn principal`.

## Decisão

### 1. Modelo

`async`/`await` **stackless, colored, single-thread, cooperativo e determinístico**. Não há
paralelismo, preempção, `spawn` destacado nem duas tarefas rodando ao mesmo tempo: o
scheduler roda uma tarefa até ela suspender.

### 2. Sintaxe

- `async fn` é modificador de declaração de função e de método: `async fn f(...) -> T`.
- `await expr` é expressão unária. Só é permitido dentro de função/método `async` **ou** no
  topo do script (modo script; o runner é a fronteira async). Precedência: `await a + b` =
  `(await a) + b`; `await f(x).y` = `await (f(x).y)`; `await a ** b` = `await (a ** b)`.
- `init` **não** pode ser `async`: `Classe(...)` devolve a instância, não um `Task`.
- Lambdas `async` ficam fora por ora.

### 3. Tipos

- `Task[T]` é tipo genérico embutido, como `List[T]`/`Map[K, V]` — não depende de T6
  (classes genéricas).
- `async fn f(...) -> T` tem tipo `fn(...) -> Task[T]`; a chamada devolve `Task[T]`;
  `await` devolve `T`.
- Anotações: `Task[T]` é a forma canônica; `async fn(...) -> T` é açúcar aceito em posição
  de tipo e desugara para `fn(...) -> Task[T]`.
- `Task` é **covariante** (produtor imutável): `Task[Dog]` é atribuível a `Task[Animal]`.
- Funções síncronas podem **produzir** `Task[T]` (devolver/guardar), mas só `async`
  **consome** com `await`.
- `await` em não-`Task`/`Any` é erro de `--check`; em runtime, erro fatal
  `Only tasks can be awaited.`.
- `Task` é namespace nativo reservado (como `Int`/`math`) e entra no prelúdio; uma classe de
  usuário chamada `Task` deixa de ser permitida.

### 4. Consumo, erros e combinadores

- Não existe `.then`, executor de promise nem assimilação de thenable. Consumir é `await`
  ou `Task.all` — é o I2 aplicado.
- `Task.all(xs: List[Task[T]]) -> Task[List[T]]`, com **ordem preservada** nos resultados,
  independente da ordem de conclusão.
- Não há `race`/`any` (não determinísticos) nem `allSettled` (só faz sentido com `Result`,
  pós-`try`).
- Tarefa é **eager**: a chamada agenda; o scheduler executa quando a tarefa corrente
  suspende. O script **drena** as pendentes ao final.
- Falha de tarefa é **fatal no ponto em que acontece** (exit 70), como qualquer erro da
  1.0. Não há unhandled rejection porque o processo não continua; `await` de tarefa falhada
  não chega a ocorrer.
- Uma tarefa executa uma vez; `await` repetido devolve o mesmo resultado. Se nenhuma tarefa
  estiver pronta e houver pendências, o loop falha com erro fatal (`Deadlock.`).
- `repr`/`str` de `Task` é constante (`<task>`), sem estado nem endereço (I3). `==` entre
  Tasks é erro; `Task` não é hashável (não serve de chave de `Map`).

### 5. Determinismo e escopo do I3

- Fila FIFO de tarefas prontas, uma por vez, sem preempção; a ordem de criação é a ordem de
  execução.
- I3 vale para tarefas **puras** (sem I/O): mesma entrada ⇒ mesma intercalação. Golden
  cases podem fixar a ordem dos `print`.
- Com I/O real, a ordem de conclusão é externa (SO/rede). Programas com I/O concorrente
  ficam **fora do I3 e do corpus diferencial** — como `time` —, exceto I/O
  determinístico/mockado. A spec deve dizer isso quando o `io` existir.

### 6. Oracle e backend

- O **tree-walk implementa primeiro** e é normativo. A técnica de suspensão do
  interpretador (colorir de `async def`, threads verdes ou caminho duplo) fica para o ADR
  de implementação, com `make bench` antes/depois; a semântica não muda.
- Backend: lowering para **máquina de estados manual** (split em cada `await`, frame no
  heap, `switch` de retomada). Não depender de `llvm.coro` (o `llvmlite` 0.50 não roda
  `CoroSplit`); não usar threads no runtime inicial.
- L4/L6 devem manter **frames materializáveis** e um GC que enxergue frames suspensos. Com
  Boehm, frames stackless são heap e não exigem registro de pilha. Revisar o
  [ADR-0031](0031-backend-nativo.md) quando o L4 começar.

### 7. Quando entra

Nada de async na 1.0. A ordem é:

1. **M5 fechado** (tipos) — antes disso, `Task[T]` brigaria com generics de classe e
   traits.
2. **Arquitetura preparada no M7** (L4/L6): frames materializáveis, GC compatível e ABI que
   não fixe "tudo na pilha nativa".
3. **Feature só quando houver I/O** (módulos + `io`): sem nada para esperar, async não passa
   no portão do [ADR-0014](0014-identidade-e-invariantes.md) ("a ausência dói").
4. **Antes do M8** (performance): não otimizar em cima de uma ABI síncrona para introduzir
   suspensão depois.
5. Implementação: oráculo (tree-walk) → golden/determinismo → backend → corpus diferencial.

`async`/`await` já são palavras-chave (reserva antecipada, ainda sem sintaxe) e `Task`
entra no prelúdio quando a sintaxe chegar; nenhum programa do corpus usava esses nomes,
então a reserva não quebrou nada.

### 8. Fora desta direção

Paralelismo/threads (em avaliação no [`IDEIAS.md`](../../IDEIAS.md) I-7),
cancelamento/timeouts, `spawn` destacado, `race`/`any`, lambdas async, `init` async,
`for await` e `llvm.coro`/toolchain LLVM externa. Cada um, se vier, pede ADR próprio.

## Consequências

### Positivas

- Cabe no backend sem runtime de threads: state machine é o caminho trilhado
  (Kotlin/C#/Rust).
- Determinismo preservado para tarefas puras; o I3 continua testável byte a byte.
- Combina com Boehm: frames suspensos são objetos no heap.
- Uma semântica só (oráculo), sem `thenable`/executor para divergir.
- Top-level await elimina o `async main` e limita a cor ao que realmente espera.

### Negativas / custos

- **Colored**: quem chama e quer o valor precisa ser `async`; HOFs com callback async são o
  ponto dolorido (sem traits, ou variantes na stdlib, ou nada).
- Anotar `fn(...) -> Task[T]` em callbacks é cerimônia; o açúcar `async fn(...)` alivia.
- Tree-walk: colorir custa em todo programa; a técnica ainda não está escolhida.
- Backend: split de estado é L/XL e cresce com `and`/`or`/`?.`/`for-in`/interpolação
  contendo `await`.
- Inerte até existir I/O: async não acelera CPU; é sobre esperar.
- O corpus diferencial ganha uma dimensão nova (ordem de intercalação) e precisa de casos
  próprios.

### Neutras

- `Task` reusa a infra de tipo embutido de `List`/`Map` no checker.
- `--dump-ast` ganha um nó `Await`; `--check` ganha `Task[T]` e a regra de contexto.
- `async`/`await` reservadas e `Task` no prelúdio são mudanças de superfície, mas baratas
  agora (nenhum uso no corpus).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Colorless stackful (Go, Lua, Java Loom, fibras) | Melhor UX, mas exige pilhas separadas/troca de pilha no runtime nativo, registro de cada pilha no Boehm e um scheduler próprio — um projeto de runtime inteiro. No tree-walk seria fácil; no LLVM, não. |
| Inferência de efeito (Koka, OCaml 5): sem anotar `async` | Tira a anotação, não tira a cor: a chamada ainda devolve `Task` e o chamador ainda precisa esperar. Complexidade de unificação; fica como qualidade de vida futura, se doer. |
| `await` implícito / "tudo pode bloquear" | Viola o I2: espera invisível e erro em ponto não escrito. |
| Promises com `.then` (callbacks) | Implementável sem suspensão, mas sem leitura linear, sem erro no ponto e sem oráculo simples. É o pior dos dois mundos; o JS só ficou usável com `async`/`await`. |
| CPS global (toda função vira máquina de estados) | Custo em todo código, debug ruim, foge do tree-walk normativo. |
| Goroutines + threads compartilhadas | É paralelismo: quebra I1/I3 e exige modelo de memória/locks. Ver IDEIAS I-7. |
| `llvm.coro` + `opt` externo | `llvmlite` 0.50 não expõe `CoroSplit`; exigiria casar a toolchain LLVM com a embutida. Revisitar só se o lowering manual se mostrar caro. |

## Como verificar (quando implementar)

- Golden cases: ordem de `print` entre tarefas, `Task.all` preservando ordem, falha de
  tarefa (exit 70), `repr(task)` estável, `==` recusado, `await` fora de async (exit 65).
- `tests/test_determinism.py` com casos async puros.
- Diferencial tree-walk × LLVM no corpus async, três canais (I1).
- `make bench` antes/depois da coloração do tree-walk, com rebaseline intencional e
  explicado.

## Critérios para revisitar

- Se a coloração se mostrar insuportável na prática → novo ADR para colorless/stackful (e o
  custo no backend é o preço).
- Se `io` nunca entrar, async não paga o portão e fica parado.
- Se o `llvmlite` expuser coro (ou a toolchain externa se justificar) → reavaliar o
  lowering.
- Se T6/traits entrarem → HOFs async ficam mais baratas; revisar a stdlib.
- Cancelamento/timeouts/`spawn`/`race` pedem ADR próprio quando houver caso de uso.

## Referências

- *What Color is Your Function?* — Bob Nystrom:
  <https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/>
- Promises e `async`/`await` (MDN):
  <https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise>
- Goroutines e scheduler do Go: <https://go.dev/doc/effective_go#goroutines>
- Java virtual threads (Loom): <https://openjdk.org/jeps/444>
- LLVM Coroutines: <https://llvm.org/docs/Coroutines.html>
- [ADR-0014](0014-identidade-e-invariantes.md), [ADR-0031](0031-backend-nativo.md),
  [`../../TODO.md`](../../TODO.md) §9, [`../../IDEIAS.md`](../../IDEIAS.md) I-7.
