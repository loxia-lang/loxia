# TODO — Roadmap e ideias

Documento vivo do projeto: o que **falta** na linguagem, no checker, no runtime e no
backend. O que já foi implementado não fica aqui: vira ADR, [`docs/spec/`](docs/spec/) e
[`docs/decisoes.md`](docs/decisoes.md). Discussões em aberto ficam em
[`IDEIAS.md`](IDEIAS.md); tipos e números em [`TIPOS.md`](TIPOS.md).

> **Escopo:** nada neste arquivo é 1.0. O escopo 1.0 está congelado no
> [ADR-0026](docs/adr/0026-freeze-1.0.md) (com T3b/D-8 como exceções); este TODO é
> **pós-1.0**. Para o mapa completo, veja [`ESCOPO.md`](ESCOPO.md).

**Legenda:** `P0` agora · `P1` próximo · `P2` depois · `P3` algum dia
**Esforço:** `S` (horas) · `M` (dias) · `L` (semanas) · `XL` (meses)

> Regra de ouro: a linguagem precisa **fechar semanticamente** antes do backend.
> Cada feature nova entra com teste; cada mudança de sintaxe entra documentada no mesmo commit.

---

## 0. Agora

O Lox do livro (caps. 4–13), o freeze da 1.0, generics T3b, `--debug`, casts/parse e
`math.*` estão feitos. **Próximo:** backend LLVM (L0–L2) ou o pacote de diagnósticos
(spans → caret → stack trace). **Depois:** tuplas (ADR-0030), classes/métodos genéricos e
constraints.

---

## 1. Sintaxe pendente

**Estrutural**
- [ ] `P2` parênteses opcionais na condição (`if x > 0 print x`) — precisa de delimitador
      entre condição e corpo (nova linha ou `then`).
- [ ] `P2` corpo de expressão em `fn` (`fn dobro(x) -> x * 2`).
- [ ] `P2` bloco como expressão (último valor do bloco é o valor).
- [ ] `P3` `match` estrutural com `=>` e exaustividade para enum/união.
- [ ] `P3` `loop { }` infinito e `break`/`continue` com rótulo.

**Operadores e literais**
- [ ] `P2` strings multilinha (`"""`) e raw strings (`r"..."`).
- [ ] `P2` indexação de string e UTF-8 completo em identificadores (hoje só `len`).
- [ ] `P3` spread `...lista` em chamadas e literais.

**Dados e funções**
- [ ] `P2` variádicos (`fn log(nivel, ...args)`); ver [`IDEIAS.md`](IDEIAS.md) I-5.
- [ ] `P2` trailing closure (`lista.map { |x| x * 2 }`) — depois do conflito com `{}`.
- [ ] `P2` tuplas: implementar a sintaxe do [ADR-0030](docs/adr/0030-tuplas.md)
      (`(a,b)`, `(A,B)`, `t[0]`, `val (a,b) = t`), pós-1.0/backend.
- [ ] `P3` argumentos nomeados e destructuring de campos.
- [ ] `P3` namespaces/imports, traits, extension methods, operator overloading,
      `type` alias e `derive`.

**Erros**
- [ ] `P2` `throw`/`try`/`catch`/`finally` e stack trace; alternativa: `Result<T, E>`.
      Fora da 1.0 ([ADR-0026](docs/adr/0026-freeze-1.0.md)).
- [ ] `P2` `assert`/`panic`/`exit` nativos.
- [ ] `P3` `Result`/`Option` como erros esperados; depois de generics de classes + `match`.

---

## 2. Tipos: o que ainda falta

O checker gradual (T1/T2/T3a/T3b) e D-8 estão feitos; detalhes em
[`TIPOS.md`](TIPOS.md) e [ADR-0027](docs/adr/0027-generics-t3b.md).

| Etapa | O que falta | Ganho |
| --- | --- | --- |
| **T3c** ⬜ | parâmetro sem anotação vira `TyVar`; unificar a cada chamada | inferência de parâmetro |
| **T4** ⬜ | generalização (let-polymorphism) → funções genéricas implícitas | bibliotecas |
| **T5** 🟡 | narrowing restante: merge de fluxo, campos/índices e invalidação por mutação | expressividade |
| **T6** ⬜ | traits/protocolos estruturais e exaustividade no `match` | abstração |
| **T7** ⬜ | monomorfização e integração com o codegen | backend sabe layouts |

Pendências pontuais:
- [ ] `P2` narrowing de campos/índices e merge completo de fluxo.
- [ ] `P2` exaustividade em `match`/enum.
- [ ] `P3` flow-sensitive para `val` (uma atribuição só).
- [ ] `P3` generics com constraints (`T with Show`), classes/métodos genéricos, type
      application explícita (`id[Int] (1)`) e função genérica como valor.
- [ ] `P3` inferência de retorno para funções com corpo de expressão.
- [ ] `P3` `--check --json` com spans para editor/LSP.

Modelo atual em [`src/ty.py`](src/ty.py): primitivos, `List[T]`, `Map[K,V]`, `FnTy`,
`ClassTy`/`ClassObjectTy`, `NativeModuleTy`, `UnionTy`, `TyVar`, `GenericFnTy` e `Never`.
`Any` é escape no tree-walk, mas o backend L0–L2 o rejeita.

---

## 3. Runtime e semântica (depois do livro)

### 3.1 Diagnósticos profissionais (P2, L)

**Hoje (resolvido):** `ErrorReporter` é uma instância por execução — `Lox.run` cria,
injeta em scanner/parser/interpreter e `reset()` no início de cada run. Não existe mais
estado global de classe, então erro de uma execução (ou de uma linha do REPL) não vaza
para a próxima. É simples de propósito; o desenho profissional é o abaixo.

- [ ] `Diagnostic` imutável: `severity` (error/warning/note/help), `code` (`E0102`),
      `span` (arquivo, linha, coluna, offset, largura), `message`, `labels[]`, `notes[]`.
- [ ] **Coleta separada de renderização**: o reporter só acumula; quem imprime é um
      `Renderer` (TTY colorido, texto puro, JSON). Hoje `ErrorReporter.report` imprime
      direto — quebrar isso permite testar diagnóstico sem capturar stderr.
- [ ] `SourceFile` com cache de linhas e coluna correta com tabs/Unicode → caret preciso.
- [ ] Dedup por `(code, span)`, limite `--max-errors` e supressão de erros em cascata
      (panick mode): um erro de sintaxe não deve gerar 20 erros derivados.
- [ ] **Códigos estáveis** documentados em `docs/erros.md`: `E0xxx` lexer, `E1xxx`
      parser, `E2xxx` resolver, `E3xxx` tipos, `E4xxx` runtime. Testes citam o código.
- [ ] Mensagens com ação: `expected ';'` + `ajuda: adicione ';' ao fim da linha 3` +
      `nota: declarações terminam com ';' por enquanto`.
- [ ] Erros de tipo com proveniência: `expected Float, found String` + "o valor vem de
      `pessoa.nome` (linha 7)".
- [ ] Warnings que não interrompem a execução; `-Werror` no CI para tratá-los como erro.
- [ ] `--json` com a lista de diagnósticos (mesma estrutura do LSP) para editor e CI.
- [ ] Stack trace de runtime com frames: `at fib (linha 4) ← main (linha 9)`.
- [ ] `Result`/`Option` para erro esperado; `throw`/`try` só para o excepcional.
- [ ] Mesmos `Diagnostic` alimentam `textDocument/publishDiagnostics` no LSP (P3).
- [ ] Testes de diagnóstico: snapshot de `(code, span, message)` e golden de stderr.
- [ ] **Schema JSON v1** com `code`/`kind`/`span` (offset em bytes + linha/coluna)/
      `fixes[]`/`docs`, versionado em `schema_version`, com teste de determinismo
      (mesmo input → bytes idênticos). Desenho em [`IDEIAS.md`](IDEIAS.md) I-4.
- [ ] `--error-format=human|short|json|json-lines`; `lox explain <code> --json` e
      `lox capabilities --json` (versão, schema, códigos, exit codes).
- [ ] Resolução determinística: ordenar por `(file, offset, code)`, dedup, sem timestamp/
      endereço/caminho absoluto, um erro raiz por causa.

**Anti-metas:** não usar `assert` do Python para validar código do usuário (assert pode
ser desligado com `-O` e não tem span); não engolir exceção; não imprimir direto do
scanner/parser (só coletar); não usar exceção Python como controle de fluxo normal.

### 3.2 Runtime e linguagem

- [ ] `P1` **stack traces**: frame com nome da função + linha, `Error: ... at foo (linha 12)`.
- [ ] `P1` **spans** (linha + coluna + offset) em `Token`; hoje só tem `line`. Sem isso
      não existe erro bonito nem LSP.
- [ ] `P1` **diagnósticos com caret**:
      ```
      erro: operando precisa ser número
        --> exemplos/x.lox:3:9
        3 | print 1 + "a"
          |         ^^^ encontrado String
      ```
- [ ] `P2` **recuperação de erro no parser** (múltiplos erros por execução).
- [ ] `P2` **`assert`/`panic`/`exit`** nativos.
- [ ] `P2` **`try/catch/finally`** se a decisão for exceções (§1); fora da 1.0
      ([ADR-0026](docs/adr/0026-freeze-1.0.md)).
- [ ] `P2` **REPL multiline** (continua enquanto `(`/`{`/`[` abertos) + histórico
      (`readline`) + `:help`, `:ast`, `:type expr`, `:clear`.
- [ ] `P3` **`import`/módulos** com cache de compilação.
- [ ] `P3` **interpolação de `toString`** customizável por classe (`__str__`).

### 3.3 Contratos (Design by Contract) — P2, M

- [ ] `requires` / `ensures` / `invariant` como cláusulas opcionais entre assinatura e
      corpo; `result` no `ensures` e `old(expr)` para o estado de entrada.
- [ ] Expressões de contrato **puras** (sem I/O/atribuição); o checker impõe.
- [ ] Violação é erro fatal **estruturado** (`C1xxx`, `kind: contract_violation`), não
      exceção capturável por `try/catch`.
- [ ] `--contracts=off|check|warn` (default `check` no interpretador, `off` no nativo).
- [ ] Invariante de classe checado na entrada/saída de métodos públicos; herança com
      pré-condições enfraquecidas e pós-condições fortalecidas (Liskov).
- [ ] Contratos como oráculo de property-based testing (conecta com o fuzzing do §7).
- [ ] Codegen: cláusula vira branch + chamada de panic; **nunca** `llvm.assume` sem
      checagem (violação seria UB, não erro).

Sintaxe, opcionalidade e protocolo de reparo: [`IDEIAS.md`](IDEIAS.md) I-4.

---

## 4. Performance do interpretador (antes do LLVM)

Objetivo: não otimizar por otimizar, mas **não deixar o oráculo lento demais** para os
testes diferenciais.

- Benchmark harness e baseline já existem (`make bench`); casos: `loop_sum`,
  `nested_loop`, `branchy`, `string_concat`.
- [ ] `P2` resolver já com **slots** (índice inteiro) em vez de dict de nomes.
      É o maior ganho por linha de código no tree-walk.
- [ ] `P2` `Environment` com lista + profundidade em vez de dict encadeado.
- [ ] `P3` inline caching de `Get`/métodos.
- [ ] `P3` novos casos de benchmark: `fib` recursivo, criação de objetos/`Get`,
      `List`/`Map` e (depois) tuplas/generics.
- [ ] `P3` `--profile` simples (contagem de nós visitados).

> Não vale reescrever o interpretador em Cython/PyPy agora. O alvo é LLVM.

---

## 5. Bytecode: fazer ou não?

**Decisão provisória: não** (por enquanto). Motivos:

- o alvo final é **LLVM**, não uma VM própria;
- uma VM intermediária em Python não é rápida o suficiente para justificar o desvio;
- o tree-walk é a **especificação executável** da linguagem — ótimo para teste diferencial.

Quando reconsiderar: se o codegen LLVM ficar complexo demais para debugar, um "HIR"
(IR própria, tipada, em SSA leve) cumpre o papel sem virar VM. Um bytecode só faria
sentido como *exercício* do livro (Parte III), em repositório separado.

---

## 6. LLVM: o objetivo final

### 6.1 Escolha de ferramenta

| Opção | Prós | Contras |
| --- | --- | --- |
| **`llvmlite`** (recomendado) | `pip install`, LLVM embutido na wheel, `ir` builder + `binding` + MCJIT (REPL!), emite `.ll`/`.o` | API limitada (sem EH nativo fácil, debug info pobre), versão de LLVM presa à wheel |
| Emitir **`.ll` textual** + `clang`/`llc` | zero dependência, IR legível e debugável, aprende LLVM de verdade | dois subprocessos, linking manual, erro de sintaxe só no `llc` |
| Transpilar para **C** | MVP em dias, ótimo para validar semântica | não é LLVM, perde tipos, vira dívida |
| `inkwell` (Rust) | cobertura completa | reescrever o compilador em Rust |

Plano: **`llvmlite` para construir o módulo**, com `--emit=ll` para inspecionar o IR e
`clang` como linker. Isso dá JIT no REPL e binário nativo no mesmo caminho.

### 6.2 Pipeline

```
AST → Resolver → TypeChecker (tipos concretos/monomorfizados)
    → HIR tipada (expressões com tipo, slots, depth)
    → LLVM IR (llvmlite.ir)
    → otimização (passes) → object file → clang → executável
                              └→ MCJIT (modo `lox jit` / REPL)
```

Por que passar por HIR: o LLVM IR exige SSA e tipos concretos. A HIR é onde ficam as
decisões da linguagem (boxing, slots, ordem de avaliação); o codegen só traduz.

### 6.3 Representação de valor (a decisão mais importante)

Começar simples e evoluir:

| Versão | Representação | Quando |
| --- | --- | --- |
| V0 | `i64` só para inteiros; sem float/string | primeiro "hello, 42" compilado |
| V1 | `i64` **tagged**: 3 bits baixos = tag (`0` int, `1` bool, `2` nil, `3` ptr, `4` float*) | MVP completo de expressões |
| V2 | ponteiro para struct `{ i8 tag, [N x i8] payload }` | objetos/classes |
| V3 | NaN-boxing (`f64` com payload nos bits) | otimização, depois que tudo funciona |

Regras:
- inteiros pequenos sem alocar (tagged).
- **`Int` e `Float` separados** (i64 + f64), decidido em
  [ADR-0006](docs/adr/0006-int-float-separados.md) — para LLVM, separar é bem melhor
  (`i64` vs `double`, sem boxing no caminho quente).
- string = `{ i64 len, i8* data }` imutável; concatenar aloca.
- toda operação aritmética tem caminho rápido desboxado e fallback que chama o runtime.

### 6.4 Runtime em C (`runtime/runtime.c`)

Funções chamadas pelo código gerado — mantém o IR pequeno e legível:

```c
void lox_print_int(i64 v);
void lox_print_float(double v);
void lox_print_str(LoxStr* s);
LoxStr* lox_str_concat(LoxStr* a, LoxStr* b);
void* lox_alloc(size_t n);
void lox_panic(const char* msg);
void lox_throw(LoxValue v);   // se exceções entrarem
```

Compilar o runtime como `.o`/`.a` e linkar com `clang`. `main` gerado só chama
`lox_entry()` e devolve 0.

### 6.5 GC

- **Fase 1:** Boehm GC (`GC_malloc`, linkar `-lgc`). Roda em 20 minutos e evita
  use-after-free enquanto o codegen amadurece.
- **Fase 2 (talvez):** alocador por arena + sem liberar (CLI curta) — simples e rápido.
- **Fase 3 (talvez):** GC preciso com shadow stack — só se o projeto virar sério.
- Referência: *Mapping High-Level Constructs to LLVM IR* (capítulo de GC) — ver §12.

### 6.6 Closures e classes

- **Closure:** no momento da criação, alocar `struct { fnptr, i8* env }`; `env` é uma
  struct com os capturados. Para mutação compartilhada, capturar **células** (heap
  `{ value }`) como o clox faz com upvalues.
- **Classe:** `struct { vtable*, fields... }`; vtable = array de fn pointers na ordem
  dos métodos (determinística). Herança = prefixo compatível de fields + vtable copiada.
- **`super`:** slot fixo na vtable / chamada direta à implementação da base.
- **Generics:** monomorfizar em compile-time (precisa do type checker!) — é o que
  permite `List[Int]` virar `[N x i64]` sem boxing.

### 6.7 Riscos conhecidos

| Risco | Mitigação |
| --- | --- |
| exceções em LLVM (`invoke`/landingpad) são difíceis | começar com `setjmp/longjmp` no runtime; ou `Result` na linguagem |
| GC + LLVM não têm integração nativa | Boehm; ou arena sem free |
| debug info ruim no llvmlite | `--emit=ll` + `lli` no começo; DWARF depois |
| ABI/linking em Windows | usar `clang` como driver, sempre; testar cedo |
| otimizar antes de funcionar | `-O0` até passar a suíte inteira; depois ligar passes |
| erros de codegen são crípticos | verificar módulo (`mod.verify()`), testes pequenos por feature |

### 6.8 Marcos do backend

- [ ] **L0 — Hello, IR**: `fn main() -> Int { 42 }` vira `.ll`, compila com `clang`,
      `./a.out` retorna 42. `--emit=ll|obj|exe`.
- [ ] **L1 — Aritmética**: `Int` tagged, `+ - * / %`, comparações, `if`, `while` com
      `phi`/blocos básicos; `println` via runtime.
- [ ] **L2 — Variáveis e funções**: `alloca`/`mem2reg`, chamadas, `return`, aridade
      checada em compile-time.
- [ ] **L3 — Strings**: literais em globals, concatenação, interpolação, `print`.
- [ ] **L4 — Closures**: env struct, captura por valor e por célula.
- [ ] **L5 — Objetos**: classes, métodos, `this`, herança, vtable.
- [ ] **L6 — Tipos**: `Int`/`Float` desboxados, monomorfização de generics, `List`/`Map`.
- [ ] **L7 — Qualidade**: `mod.verify()`, passes `-O2`, testes diferenciais
      interpretador × nativo, benchmarks, JIT no REPL, mensagens de erro de codegen.

### 6.9 CLI alvo

```bash
lox run script.lox            # interpretador (hoje: main.py)
lox check script.lox          # só typecheck/resolver
lox build script.lox -o app   # nativo
lox build script.lox --emit=ll        # inspecionar LLVM IR
lox build script.lox --emit=obj       # .o para linkar
lox jit script.lox            # MCJIT, sem arquivo intermediário
lox fmt script.lox            # formatador (dogfooding do parser)
lox repl                      # REPL, com :type, :ast
```

### 6.10 Bônus: WebAssembly

`llvmlite` sabe emitir para **wasm32** (`Target.from_triple("wasm32-unknown-unknown")`).
Isso permitiria um playground no navegador sem Pyodide — a linguagem rodando a 100% no
browser. Guardar como ideia P3 (precisa de runtime mínimo em wasm e de uma ABI de
imports para `print`).

---


## 7. Tooling e qualidade

- [ ] `P2` testes diferenciais interpretador × LLVM (mesmo stdout, exit code).
- [ ] `P2` CLI agent-friendly: `--json` em `check`/`ast`/`types`/`fmt`, `--no-progress`,
      `--timeout`, sem prompt interativo, exit codes estáveis (checklist em
      [`IDEIAS.md`](IDEIAS.md) I-4).
- [ ] `P3` fuzzing do scanner/parser com `hypothesis`.
- [ ] `P3` snapshot de AST em arquivo.
- [ ] `P3` tree-sitter grammar + LSP mínimo (diagnostics/hover).
- [ ] `P3` `lox fmt` e teste de idempotência.
- [ ] `P3` site publicado (mkdocs/mdbook) a partir de `docs/`.

Infra já pronta: pytest (golden `.lox`; 678 pass + 8 `xfail`), ruff, mypy strict,
`make check`, pre-commit, CI, skills e docs com teste de links.

---

## 8. Lox2: o que ainda vale

| Recurso | Status | Nota |
| --- | --- | --- |
| `for-in` + iterador de usuário | ⏳ | o `for-in` embutido existe; falta protocolo de usuário |
| `print` como função (`println`) | ⏳ | depois da 1.0; statement é a decisão |
| variádicos `...args` | ⏳ | falta implementar |
| trailing closure | ⏳ | falta implementar |
| `type` alias | ⏳ | falta implementar |
| generics + constraints/traits | ⏳ | funções T3b prontas; constraints depois de T4 |
| uniões + narrowing | 🟡 | `T?`/`is`/`while` prontos; falta campos/índices e merge |
| traits + `with` | ⏳ | depois de classes |
| operator overloading | ⏳ | depois de classes |
| namespaces/import | ⏳ | necessário com stdlib |
| `throw`/`try` | ⏳ | caro no LLVM |
| `match` estrutural | ⏳ | depois de uniões/enums |
| extension methods | ⏳ | depois do LLVM MVP e de traits |
| classes como valores / metaclasses | 🤔 | só se precisar |
| FFI com C | ⏳ | depois de linking estável |
| stdlib (`io`, `string`, `collections`) | ⏳ | mínima primeiro |

Fora: VM própria, GC geracional, async/await, JIT tracing, cache de bytecode e
`Object` raiz — o LLVM cobre o codegen e o escopo humano manda.

---

## 9. Milestones pendentes

M0–M4 (livro, sintaxe, tipos T1/T2/T3a/T3b e D-5/D-8) estão fechados. Falta:

| # | Marco | Critério de pronto |
| --- | --- | --- |
| **M5** | Tipos v2 | T4–T6: classes/métodos genéricos, constraints/traits, narrowing completo e exaustividade |
| **M6** | HIR + LLVM MVP | L0–L2: inteiros, controle de fluxo, funções e binário nativo; I1 verde no corpus |
| **M7** | Runtime completo | L3–L5: strings, closures, classes e GC; I1 verde no corpus completo |
| **M8** | Performance | L6–L7: desboxar tipos, monomorfizar, `-O2`, benchmarks e JIT |
| **M9** | Ecossistema | formatter, LSP, docs, CI e playground |

Regra: M6 só começa com M5 verde (tipos v2); sem isso o codegen persegue uma linguagem que ainda muda.

---

## 10. Parque de diversões (ideias soltas)

- [ ] **Compilar o próprio interpretador?** (self-hosting) — irrealista, mas o exercício
      de escrever `loxc` em `.lox` ensina muito. P3/XL.
- [ ] **Playground WASM** (target `wasm32` do LLVM) rodando no navegador.
- [ ] **REPL com `:type`** — mostra o tipo inferido de uma expressão antes de rodar.
- [ ] **`lox test`** — runner de testes embutido na linguagem (`#[test] fn ...`).
- [ ] **Erros com sugestão** ("você quis dizer `println`?" via distância de edição).
- [ ] **Debugger (DAP)** — breakpoints no tree-walk primeiro; no nativo depois.
- [ ] **Hot reload** no REPL (redefinir funções sem perder estado).
- [ ] **Benchmark suite pública** (fib, nbody, mandelbrot) para acompanhar regressões.
- [ ] **Compilar para um Arduino/Pico?** (LLVM target `thumbv6m`) — suicídio de escopo,
      mas divertido de tentar um dia.
- [ ] **Dialeto embutido**: `lox` como linguagem de script de um app Python (via CFFI).
- [ ] **Gerador de AST a partir de schema** (o livro faz à mão; um script evita erro
      quando a linguagem crescer).
- [ ] **`lox doc`** — gera docs a partir de comentários de documentação (ex.: `##`).
- [ ] **Modo "strict"** vs "loose" para compatibilidade com Lox puro durante a transição.

---


## 11. Decisões em aberto

Só o que ainda não foi decidido. Fechadas: [`docs/decisoes.md`](docs/decisoes.md); tipos:
[`TIPOS.md`](TIPOS.md) §10.

1. **Generics além de funções:** classes/métodos genéricos, constraints/traits, type
   application explícita e função genérica como valor; monomorfização já decidida
   ([ADR-0027](docs/adr/0027-generics-t3b.md)).
2. **Backend:** `llvmlite` desde o começo ou `.ll` textual + clang primeiro? (tende a
   `llvmlite`).
3. **Nome e extensão** definitivos (hoje "PyLox", `.lox`; nomes de trabalho na 1.0).
4. **Stdlib pós-1.0:** `io`, `string`, `collections`, `time` não determinístico;
   transcendentais de `math` fora do I3.
5. **Tuplas:** implementação pós-1.0/backend ([ADR-0030](docs/adr/0030-tuplas.md)).
6. **Contratos e agentes:** `requires`/`ensures`/`invariant`, `--contracts` default e JSON
   schema v1 com `fixes[]` — [`IDEIAS.md`](IDEIAS.md) I-4.
7. **`if`/bloco como expressão, `match`/enums e traits:** fora da 1.0; reavaliar depois
   do backend/M5.

---

## 12. Referências

- Livro: <https://craftinginterpreters.com/> — e a suíte de testes oficial em
  <https://github.com/munificent/craftinginterpreters/tree/master/test>.
- Lox2: <https://github.com/HallofFamer/Lox2> · docs <https://mysidia-inc.gitbook.io/lox2>
  (ler `notes/DESIGN.md` e `notes/TYPESYSTEM.md`).
- `llvmlite`: <https://llvmlite.readthedocs.io/> · <https://github.com/numba/llvmlite>
- LLVM LangRef: <https://llvm.org/docs/LangRef.html> · tutorial Kaleidoscope:
  <https://llvm.org/docs/tutorial/>
- *Mapping High-Level Constructs to LLVM IR*:
  <https://mapping-high-level-constructs-to-llvm-ir.readthedocs.io/> (closures, vtables, GC)
- Hindley–Milner (para o modelo mental de unificação):
  <https://en.wikipedia.org/wiki/Hindley%E2%80%93Milner_type_system>
- Crafting Interpreters, cap. 11 (resolver) e cap. 26 (GC) — reler quando chegar a vez.