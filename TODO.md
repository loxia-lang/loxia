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

> Regra de ouro: fechar as definições que cada nível consome **antes** de codá-lo
> (checklist na §0.1). Cada feature nova entra com teste; cada mudança de sintaxe entra
> documentada no mesmo commit.

---

## 0. Fila única

Esta é a **ordem oficial**. As seções 1–12 são o catálogo de detalhes; se houver conflito,
vale o que está aqui. Estado em 2026-11-13: **104 golden cases** (64 compilam, 38 `PENDING`
por nível, 2 negativos), corpus oficial anotado, backend em **L0–L4 + L2.5 + L5a/L5b/L5c parcial**, M5
fechado e ADRs 0043–0048 (layout, identidade, narrowing, L4, optionais escalares e ABI de
classes) fechados.

### 0.1 Definições que não podem faltar antes de cada nível

| Antes de | O que precisa estar fechado | Estado |
| --- | --- | --- |
| **L4** | ADR-0046: sem HIR, células só para capturados, funções locais/lambdas, valores de função, defaults/aridade, `print` de função e spans/stack trace fora do L4 | ✅ |
| **L5** | ADRs 0043/0044/0045/0048 + L5a/L5b implementados (classes, campos/bitmap, métodos/`this`/`init`, bound methods, herança/vtable/`super`, `print`); L5c (`?.` opcional, classes locais, `is`/`as`) pendente | 🟡 |
| **L6** | T7 (monomorfização), `Any` boxeado, representação numérica unificada, exceções (unwinding), enums/`match`, `List`/`Map`/tuplas/`Range`/`for-in` e `print` determinístico de listas/mapas/tuplas/enums | ⬜ |

`T?` escalar apareceu como L2 na §6.3, mas o L2 fechou **sem** ele; o **L2.5** fechou a
lacuna ([ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md)). É exatamente o tipo de
lacuna que esta fila existe para não repetir.

### 0.2 Ordem de execução

1. [x] **L2.5 — optionais escalares e variáveis não inicializadas**: `T?` escalar
       (`{i1, T}`), `var x: T?;`, `nil` contextual e unwrap checado
       ([ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md)); `variables.lox`
       promovido. `var x: Int;` sem init segue `PENDING` no L6.
2. [ ] **Atribuir nível às operações escalares restantes**: `**`, bits, `as`/`math.*`,
       `chars`, `repr` de `List`/`Map`; decidir L4 × L6 e adicionar ao manifesto.
3. [x] **ADR de L4 + implementação**: [ADR-0046](docs/adr/0046-closures-celulas-l4.md),
       sem HIR, `env`/células, funções locais/lambdas, valores de função, defaults/aridade;
       casos `l4` promovidos.
4. [ ] **L5 — objetos** ([ADR-0048](docs/adr/0048-abi-classes-l5.md)):
       - [x] **L5a**: classes de topo, campos/bitmap, métodos/`this`/`init`, bound methods,
         `print` de classe/instância e construção por nome;
       - [x] **L5b**: herança, cópia/override de vtable, `super`/`super.init`, `init`
         herdado e prefixo de campos;
       - [ ] **L5c**: `is`/`as` de classe e classes locais **vazias** já funcionam
         (`class_identity`); `String?`/instância `T?` funcionam em campos/parâmetros/
         retornos. Faltam `?.` com receptor opcional, classes locais com campos/métodos/
         captura e o `nil_aware` completo (união/`Any`, L6).
5. [ ] **ADR T7 + L6 — tipos**: monomorfização, `Any`, representação numérica unificada,
       `List`/`Map`, tuplas, enums/`match`, exceções (unwinding), `Range`/`for-in`.
6. [ ] **Corpus por nível**: cada nível só fecha quando seus casos saem de `PENDING` e
       entram em `LEVELS`; I1 só vale para o corpus anotado.
7. [ ] **Diagnósticos** (spans → caret → stack trace): decisão do ADR-0046 é **fora do
       L4**; ADR próprio antes do L5/L6, porque mexem em stderr/I1.
8. [ ] **L7 — qualidade**: `mod.verify()`, `-O2`, benchmarks, JIT e mensagens de codegen.

### 0.3 Fora do caminho crítico (não bloqueiam nenhum L)

Traits/constraints (T6b, [ADR-0038](docs/adr/0038-traits-nominais.md), pós-MVP), métodos/
herança genérica/reificação (parked na §10), type application explícita, função genérica
como valor, módulos/imports, stdlib, contratos, async, tooling/LSP/formatter e performance.
Esses itens voltam quando o backend estiver no nível em que passam a doer; nenhum deles
impede L4, L5 ou L6.

### 0.4 Onde está o detalhe

| Assunto | Seção |
| --- | --- |
| sintaxe e açúcar | §1 |
| tipos, checker e narrowing | §2 + [`TIPOS.md`](TIPOS.md) |
| diagnósticos, exceções e runtime | §3 |
| performance do tree-walk | §4 |
| decisão sobre bytecode/VM | §5 |
| backend LLVM, níveis, corpus | §6 |
| tooling, CI e LSP | §7 |
| o que copiar do Lox2 | §8 |
| milestones M5–M9 | §9 |
| ideias soltas e coisas adiadas | §10 |
| decisões ainda em aberto | §11 |

---

## 1. Sintaxe pendente

**Estrutural**
- [ ] `P2` parênteses opcionais na condição (`if x > 0 print x`) — precisa de delimitador
      entre condição e corpo (nova linha ou `then`).
- [ ] `P2` corpo de expressão em `fn` (`fn dobro(x) -> x * 2`).
- [ ] `P2` bloco como expressão (último valor do bloco é o valor).
- [ ] `P3` `match` estrutural para uniões; enum/`match` exaustivo já existe
      ([ADR-0041](docs/adr/0041-enums-match.md)).
- [ ] `P3` `loop { }` infinito e `break`/`continue` com rótulo.

**Operadores e literais**
- [ ] `P2` strings multilinha (`"""`) e raw strings (`r"..."`).
- [x] `P2` acesso a caractere: `chars(s)` decidido; `s[i]` rejeitado ([ADR-0035](docs/adr/0035-strings-texto.md)).
- [x] `P2` identificadores Unicode: mantidos ASCII por decisão ([ADR-0035](docs/adr/0035-strings-texto.md)).
- [ ] `P3` spread `...lista` em chamadas e literais.

**Dados e funções**
- [ ] `P2` variádicos (`fn log(nivel, ...args)`); ver [`IDEIAS.md`](IDEIAS.md) I-5.
- [ ] `P2` trailing closure (`lista.map { |x| x * 2 }`) — depois do conflito com `{}`.
- [x] `P2` tuplas: `(a,b)`, `(A,B)`, `t[i]`, `val/var (a,b) = t`, igualdade, `len`,
      formatação, `for-in`, `is`/`as` ([ADR-0030](docs/adr/0030-tuplas.md),
      [ADR-0036](docs/adr/0036-tuplas-implementacao.md)).
- [ ] `P2` tuplas no backend (L6) e destructuring aninhado (`val (a, (b,c)) = t`).
- [ ] `P3` argumentos nomeados e destructuring de campos.
- [ ] `P3` namespaces/imports, traits nominais ([ADR-0038](docs/adr/0038-traits-nominais.md)), extension methods, operator overloading e `derive`.
- [ ] `P3` `type` alias transparente (sem generics); decisão em [ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md).

**Erros**
- [ ] `P2` subclasses específicas de runtime (`DivisionByZero`, `IndexError`, ...) e
      stack trace; hoje tudo é `LoxRuntimeError` ([ADR-0042](docs/adr/0042-excecoes.md)).
- [ ] `P2` `assert`/`panic`/`exit` nativos.

---

## 2. Tipos: o que ainda falta

O checker gradual (T1/T2/T3a/T3b) e D-8 estão feitos; detalhes em
[`TIPOS.md`](TIPOS.md) e [ADR-0027](docs/adr/0027-generics-t3b.md).

| Etapa | O que falta | Ganho |
| --- | --- | --- |
| **T3c** ❌ | parâmetro implícito foi implementado e **revertido**: omissão virava quantificação universal sem marcador, contra o [ADR-0020](docs/adr/0020-assinaturas-explicitas.md) ([ADR-0034](docs/adr/0034-t3c-revertido.md)) | — |
| **T4** ✅ | generalização de `val f = fn(...)` (let-polymorphism); `var` não generaliza | bibliotecas |
| **T5** ✅ | narrowing de campos/índices literais, invalidação por mutação/chamada e refino pós-`while` ([ADR-0045](docs/adr/0045-narrowing-representacao.md)); resta CFG/aliasing completo | expressividade |
| **T6a** ✅ | classes genéricas MVP ([ADR-0040](docs/adr/0040-generics-classes-desenho.md)); follow-ups (métodos, herança de `Box[Int]`, reificação) **adiados** (ver §10) | bibliotecas |
| **T6b** ⏸ | traits nominais com `implements` e métodos default, e constraints: decididos, **pós-MVP** ([ADR-0038](docs/adr/0038-traits-nominais.md)) | abstração |
| **T6c** ✅ | `match`/enums genéricos, exaustividade e `Result` ([ADR-0041](docs/adr/0041-enums-match.md)) | expressividade |
| **T7** ⬜ | monomorfização e integração com o codegen | backend sabe layouts |

Plano do **T6a** (desenho no [ADR-0040](docs/adr/0040-generics-classes-desenho.md)):
- [x] parser/AST/tipos: `class C[T]`, `ClassTy.args`, printer, erro de superclasse genérica.
- [x] checker: `ClassInfo` com params, `this`/`init`, resolução/aridade de `Box[Int]`.
- [x] checker: inferência no construtor (`Box(1)`, `Pair(1, "a")`, esperado pré-binda).
- [x] checker: membros substituídos, `_assignable` invariante, `_unify` de `ClassTy`, interop com funções genéricas.
- [x] runtime erasure, guards de `is`/`as` e rejeição 65 no backend.
- [x] testes, golden `generic_class.lox` e docs.
- Follow-ups do MVP (métodos genéricos, herança de `Box[Int]` e `is/as` reificado)
  **adiados**: ver §10.

Pendências pontuais:
- [ ] `P2` merge completo em CFG e aliasing fino (chamada/atribuição já invalidam refinos de
      campo/índice; `var` capturado por closure ainda não); ver
      [ADR-0045](docs/adr/0045-narrowing-representacao.md) e
      [ADR-0032](docs/adr/0032-narrowing-campos-indices.md) §Limitações.
- [ ] `P2` **T3c-v2 (HM-lite)**: inferir o tipo do parâmetro pelo **uso no corpo**
      (unificação: `x * 2` liga a `Int`, `==` generaliza), em vez de universal por omissão;
      precisa de unificação no corpo e mensagens próprias ([ADR-0034](docs/adr/0034-t3c-revertido.md)).
- [ ] `P3` flow-sensitive para `val` (uma atribuição só).
- [ ] `P3` generics com constraints (`T: Trait`), type application explícita
      (`id[Int] (1)`) e função genérica como valor.
- [ ] `P3` inferência de retorno para funções com corpo de expressão.
- [ ] `P3` `--check --json` com spans para editor/LSP.

Modelo atual em [`src/frontend/ty.py`](src/frontend/ty.py): primitivos, `List[T]`, `Map[K,V]`, `FnTy`,
`ClassTy`/`ClassObjectTy`, `NativeModuleTy`, `UnionTy`, `TyVar`, `GenericFnTy` e `Never`.
`Any` é escape no tree-walk, mas o backend L0–L4 o rejeita.

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

- [ ] `P1` **spans/caret/stack trace**: recorte mínimo da §3.1; **fora do L4** por decisão
      do [ADR-0046](docs/adr/0046-closures-celulas-l4.md), com ADR próprio antes do L5/L6;
      pré-requisito para erros bonitos e stderr do nativo.
- [ ] `P2` **recuperação de erro no parser** (múltiplos erros por execução).
- [ ] `P2` **`assert`/`panic`/`exit`** nativos.
- [ ] `P2` **REPL multiline** (continua enquanto `(`/`{`/`[` abertos) + histórico
      (`readline`) + `:help`, `:ast`, `:type expr`, `:clear`.
- [ ] `P3` **`import`/módulos** com cache de compilação.
- [ ] `P3` **interpolação de `toString`** customizável por classe (`__str__`).

### 3.3 Contratos (Design by Contract) — P2, M

- [ ] `requires` / `ensures` / `invariant` como cláusulas opcionais entre assinatura e
      corpo; `result` no `ensures` e `old(expr)` para o estado de entrada.
- [ ] Expressões de contrato **puras** (sem I/O/atribuição); o checker impõe.
- [ ] Violação é erro fatal **estruturado** (`C1xxx`, `kind: contract_violation`), não
      exceção capturável por `try`/`except`.
- [ ] `--contracts=off|check|warn` (default `check` no interpretador, `off` no nativo).
- [ ] Invariante de classe checado na entrada/saída de métodos públicos; herança com
      pré-condições enfraquecidas e pós-condições fortalecidas (Liskov).
- [ ] Contratos como oráculo de property-based testing (conecta com o fuzzing do §7).
- [ ] Codegen: cláusula vira branch + chamada de panic; **nunca** `llvm.assume` sem
      checagem (violação seria UB, não erro).

Sintaxe, opcionalidade e protocolo de reparo: [`IDEIAS.md`](IDEIAS.md) I-4.

---

## 4. Performance do interpretador (paralelo, não bloqueia o backend)

Objetivo: não otimizar por otimizar, mas **não deixar o oráculo lento demais** para os
testes diferenciais. O backend já começou; isto não é pré-requisito de L4–L6.

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

**Decidido** ([ADR-0031](docs/adr/0031-backend-nativo.md)): `llvmlite` como *extra*
opcional (`uv sync --extra llvm`), object file emitido pelo LLVM embutido e link com o
`cc` do sistema. `.ll` é artefato de inspeção (`--emit=ll`), não etapa de build — evita
descompasso entre a versão do LLVM que gera o IR e a que o parseia. Implementado no L0:
`src/backend/`, `runtime/runtime.c`, `--emit=ll|obj|exe` e `tests/test_backend.py`.

### 6.2 Pipeline

```
AST → Resolver → TypeChecker (tipos concretos/monomorfizados)
    → normalização leve (AST → AST; desugar)      ← ADR-0031, decisão 10
    → LLVM IR (llvmlite.ir)
    → object file (LLVM embutido) → cc → executável
                              └→ MCJIT (modo `lox jit` / REPL) — L7
```

Sem HIR completa no L0–L4: a normalização só desaçucara e o L4 tem só um passe de captura
(ADR-0046). Uma HIR tipada (slots, SSA leve, células) entra quando classes/L5 exigirem —
o gatilho é o `lower_expr` começar a duplicar o `interpreter.py`.

### 6.3 Representação de valor (a decisão mais importante)

**Decidido: desboxado por tipo concreto** ([ADR-0031](docs/adr/0031-backend-nativo.md)).
A ideia de `i64` tagged foi **descartada**: 3 bits de tag deixam 61 bits de payload e
conflitam com o wrap de i64 completo prometido pelo ADR-0006/0028.

| Tipo | Representação | Nível |
| --- | --- | --- |
| `Int` | `i64` (wrap nativo, sem `nsw`) | L0 ✅ |
| `Bool` | `i1` | L0 ✅ |
| `nil` | ausência (`void` no print) | L0 ✅ |
| `Float` | `double` | L1 ✅ |
| `T?` escalar | `{i1, T}` | L2.5 ✅ ([ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md)) |
| `T?` referência | ponteiro nulo | L5c 🟡 (`String?`/instância em campos/params/retornos; `?.` opcional pendente) |
| `String` | `{i64 byte_len, i64 cp_len, i8* data}` | L3 ✅ |
| closure | `{fnptr, env*, display}` (ponteiro de arena) | L4 ✅ |
| instância | ponteiro para struct `{classe, bitmap, slots i64}` | L5a/L5b ✅ ([ADR-0048](docs/adr/0048-abi-classes-l5.md)) |
| `Any` (quando entrar) | caixa `LoxValue` **só** no caminho dinâmico | L6 |

Regras:
- `Int` e `Float` separados (ADR-0006), sem boxing no caminho quente.
- `Any`, `List` cru e `Map` heterogêneo são erro de compilação até o L6.
- `//` e `%` passam pelo runtime (guarda de zero e de `INT_MIN / -1`, que é UB em LLVM).
- toda operação tem caminho desboxado; o runtime só entra onde há caso de borda ou I/O.
- `T?` escalar já tem representação `{i1, T}` e `var x: T?;` nasce nil; `var x: Int;`
  sem inicializador segue 65 até o L6. `T?` de referência é ponteiro nulo e já cobre
  `String?`/instância em campos/params/retornos; `?.` com receptor opcional fica no L5c.

### 6.4 Runtime em C (`runtime/runtime.c`)

Funções chamadas pelo código gerado — mantém o IR pequeno e legível:

```c
void     lox_panic(int32_t line, const char *msg);   // exit 70, stderr idêntico
void     lox_init(void);                            // LC_NUMERIC=C (I3) — L1 ✅
void     lox_print_int(int64_t v);                  // L0 ✅
void     lox_print_bool(int32_t v);                 // L0 ✅
void     lox_print_nil(void);                       // L0 ✅
int64_t  lox_int_div(int64_t a, int64_t b, int32_t line);  // L0 ✅
int64_t  lox_int_mod(int64_t a, int64_t b, int32_t line);  // L0 ✅
void     lox_print_float(double v);                 // L1 ✅ (menor representação)
double   lox_float_div(double a, double b, int32_t line);  // L1 ✅
double   lox_float_mod(double a, double b, int32_t line);  // L1 ✅
void     lox_print_str(const void *s);              // L3 ✅
void    *lox_str_concat(const void *a, const void *b);  // L3 ✅
int64_t  lox_str_len(const void *s);                // L3 ✅ (code points)
int32_t  lox_str_equal(const void *a, const void *b);   // L3 ✅
void    *lox_str_from_int/double/bool;              // L3 ✅ (interpolação)
void    *lox_str_nil(void);                         // L3 ✅
void    *lox_str_quote(const void *s);              // L3 ✅ (`repr`)
int32_t  lox_str_compare(const void *a, const void *b); // L3 ✅ (`< <= > >=`)
void    *lox_alloc(size_t n);                       // L3 ✅ (arena com teto)
```

O runtime é compilado por build com o mesmo `cc` do link (`.o` em diretório temporário).
`main` gerado devolve `0` no sucesso — o valor de retorno de uma função do usuário não é
exit code.

### 6.5 Memória

**Decidido** ([ADR-0031](docs/adr/0031-backend-nativo.md)): arena (bump) com teto
configurável e `lox_panic` determinístico ao estourar. `lox_alloc` é o único ponto de
alocação, então trocar por Boehm é mudar o corpo de uma função.

- **Fase 1:** arena sem `free` (CLI curta) — simples, rápida e determinística na falha.
- **Fase 2 (se rodar programa longo):** Boehm (`GC_malloc`, `-lgc`), opt-in por flag.
- **Fase 3 (talvez):** GC preciso com shadow stack — só se o projeto virar sério.
- Contagem de referência está fora: a linguagem permite ciclos (`list_cycle.lox`).
- Referência: *Mapping High-Level Constructs to LLVM IR* (capítulo de GC) — ver §12.

### 6.6 Closures e classes

- **Closure (L4 ✅):** `struct { fnptr, env, display }` na arena; `env` é uma struct de
  ponteiros para **células** (heap `{ value }`) das variáveis capturadas. Variáveis não
  capturadas continuam em `alloca` ([ADR-0046](docs/adr/0046-closures-celulas-l4.md)).
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
| `llvmlite` 0.50 mudou a inicialização (`initialize()` agora levanta) | usar só `initialize_native_target()`/`initialize_native_asmprinter()`; isolado em `llvm_ir.py` |
| ABI/linking em Windows | usar `clang` como driver, sempre; testar cedo |
| otimizar antes de funcionar | `-O0` até passar a suíte inteira; depois ligar passes |
| erros de codegen são crípticos | verificar módulo (`mod.verify()`), testes pequenos por feature |

### 6.8 Marcos do backend

- [x] **L0 — Hello, IR**: `print` de `Int`/`Bool`/`nil`, `+ - * // %`, comparações,
      igualdade e unário; `--emit=ll|obj|exe`; runtime C (`lox_print_*`, `lox_panic`) e
      teste diferencial nos três canais.
- [x] **L1 — Aritmética e controle de fluxo**: `Float` desboxado, promoção `Int → Float`,
      `/` sempre Float, `%` de Float, comparações com NaN, `if`/`while`/blocos e impressão
      de `double` pela menor representação (fuzz contra `repr`). Manifesto `l0`/`l1`.
- [x] **L2 — Variáveis e funções**: `val`/`var` com `alloca`/globais, atribuição, escopo,
      sombreamento; funções de topo com chamada direta, `return`, recursão, defaults no
      call site e **aridade/variável indefinida como panic site**; `for` C-style
      (desaçucarado pelo parser) compila. A lacuna de `T?` escalar/`var x: T?;` foi
      fechada no L2.5 ([ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md)); `T?` de
      referência entra no L5.
- [x] **L2b — Normalização**: ternário, `and`/`or` e `??` (blocos + `phi`, com
      curto-circuito e dobra de literais); `for-in` fica no L6 (depende de
      `Range`/`List`/`String`). Limitação conhecida: o slot é monomórfico, então
      `var x = 1.5; x = 2` (troca `Float`/`Int` em runtime) é rejeitado com 65 — o
      interpretador aceita; resolver junto com a representação numérica unificada (L6).
- [x] **L3 — Strings**: literais em globals, concatenação, `print`, igualdade e `len`
      (code points), **interpolação** (`"${expr}"` com `stringify` de escalares),
      `str`/`repr` (com citação/escapes) e arena de 64 MiB com panic determinístico.
      `repr` de listas/mapas entra no L6.
- [x] **L2.5 — Optionais escalares**: `T?` escalar (`{i1, T}`), `var x: T?;`, nil
      contextual e unwrap checado ([ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md));
      `variables.lox` promovido. Os campos/valores `T?` de referência entram no L5.
- [x] **L4 — Closures**: env struct, células só para capturados, funções locais/lambdas,
      valores de função, chamada indireta e `print` (`<fn f>`/`<lambda>`) — [ADR-0046](docs/adr/0046-closures-celulas-l4.md).
- [x] **L5a/L5b — Objetos**: classes, campos/bitmap, métodos/`this`/`init`, bound
      methods, herança, vtable, `super`/`super.init`, `init` herdado e `print` de
      classe/instância ([ADR-0048](docs/adr/0048-abi-classes-l5.md)).
- [x] **L5c parcial — Identidade e classes locais vazias**: `is`/`as` de classe,
      classes locais sem campos/métodos, `String?`/instância `T?` em campos/params/
      retornos. `?.` opcional e classes locais gerais ficam no L6 (união/`Any`/captura). Layout/identidade em
      [ADR-0043](docs/adr/0043-layout-l5-classes.md)/[ADR-0044](docs/adr/0044-identidade-classe.md);
      representação/narrowing em [ADR-0045](docs/adr/0045-narrowing-representacao.md).
- [ ] **L6 — Tipos**: `Int`/`Float` desboxados, monomorfização de generics, `List`/`Map`,
      tuplas, enums, exceções (unwinding), `Range` e `for-in`, mais as operações escalares
      restantes (`**`, bits, `as`/`math.*`, `chars`; nível fixado na §0.2).
- [ ] **L7 — Qualidade**: `mod.verify()`, passes `-O2`, testes diferenciais
      interpretador × nativo, benchmarks, JIT no REPL, mensagens de erro de codegen.

### 6.9 CLI alvo

```bash
lox run script.lox            # interpretador (hoje: main.py script.lox)
lox check script.lox          # só typecheck/resolver (hoje: --check)
uv run main.py --emit=ll  script.lox  # inspecionar LLVM IR (hoje)
uv run main.py --emit=obj script.lox  # .o para linkar (hoje)
uv run main.py --emit=exe -o app script.lox  # nativo (hoje)
lox build script.lox -o app   # nativo (quando o CLI ganhar subcomandos)
lox build script.lox --emit=ll        # equivalente futuro
lox jit script.lox            # MCJIT, sem arquivo intermediário
lox fmt script.lox            # formatador (dogfooding do parser)
lox repl                      # REPL, com :type, :ast
```

### 6.10 Bônus: WebAssembly

`llvmlite` sabe emitir para **wasm32** (`Target.from_triple("wasm32-unknown-unknown")`).
Isso permitiria um playground no navegador sem Pyodide — a linguagem rodando a 100% no
browser. Guardar como ideia P3 (precisa de runtime mínimo em wasm e de uma ABI de
imports para `print`).

### 6.11 Corpus diferencial (bloqueia o I1)

O I1 vale para o **corpus inteiro anotado**; a suíte oficial entra pela camada dinâmica e
cada nível promove os seus casos de `PENDING` para `LEVELS`:

- [x] anotar os 104 `tests/cases`: 64 compilam; 38 ficam `PENDING` por nível
      (`l2`, `l5`, `l6` e `l?` para as operações ainda sem nível) e 2 são negativos
      (check falha por design);
- [x] manifesto de casos por nível (`l0`–`l3`) e promoção monotônica;
- [x] CI sempre com `--extra llvm` e `LOX_REQUIRE_LLVM=1` (falha, não skip);
- [x] meta-teste de classificação: todo caso está em `LEVELS`, `PENDING` ou `NEGATIVE`;
      `PENDING` passa no `--check` e falha no backend com 65, nunca traceback/exit 1;
- [x] anotar `exemplos/classes.lox`;
- [x] anotar `tests/official/cases`: os 59 positivos passam no `--check` via camada
      dinâmica (`Any`) em [`tests/official_annotations.py`](tests/official_annotations.py),
      aplicada sobre a fonte adaptada (originais intactos); os 56 negativos esperam erro
      e os `xfail` de campos dinâmicos ficam fora ([README](tests/official/README.md)).

```bash
uv sync --extra llvm
uv run pytest tests/test_backend.py -q
```


---


## 7. Tooling e qualidade

- [ ] `P2` testes diferenciais interpretador × LLVM no corpus inteiro (hoje: L0–L4,
      comparando stdout, stderr e exit code).
- [ ] `P2` CLI agent-friendly: `--json` em `check`/`ast`/`types`/`fmt`, `--no-progress`,
      `--timeout`, sem prompt interativo, exit codes estáveis (checklist em
      [`IDEIAS.md`](IDEIAS.md) I-4).
- [ ] `P3` fuzzing do scanner/parser com `hypothesis`.
- [ ] `P3` snapshot de AST em arquivo.
- [ ] `P3` tree-sitter grammar + LSP mínimo (diagnostics/hover).
- [ ] `P3` `lox fmt` e teste de idempotência.
- [ ] `P3` site publicado (mkdocs/mdbook) a partir de `docs/`.

Infra já pronta: pytest (golden `.lox`; 1042 pass + 8 `xfail`), ruff, mypy strict,
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
| generics + constraints | ⏳ | funções T3b prontas; constraints pós-MVP, junto de traits ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| uniões + narrowing | 🟡 | `T?`/`is`/`while`/campos/índices prontos; falta merge CFG/aliasing |
| traits nominais + `implements` | ⏸ | decididos com métodos default; pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| operator overloading | ⏳ | depois de classes |
| namespaces/import | ⏳ | necessário com stdlib |
| `try`/`raise` | 🟡 | tree-walk implementado ([ADR-0042](docs/adr/0042-excecoes.md)); backend L6 (unwinding) |
| `match` estrutural em uniões | ⏳ | enum/`match` exaustivo já existe ([ADR-0041](docs/adr/0041-enums-match.md)); falta união/estrutural |
| extension methods | ⏳ | depois do LLVM MVP e de traits |
| classes como valores / metaclasses | 🤔 | só se precisar |
| FFI com C | ⏳ | depois de linking estável |
| stdlib (`io`, `string`, `collections`) | ⏳ | mínima primeiro |
| `async`/`await` | ⏳ | direção no [ADR-0037](docs/adr/0037-async-direcao.md): colored, `Task[T]`, determinístico; só com I/O, pós-M7 |

Fora: VM própria, GC geracional, JIT tracing, cache de bytecode e
`Object` raiz — o LLVM cobre o codegen e o escopo humano manda.

---

## 9. Milestones pendentes

M0–M4 (livro, sintaxe, tipos T1/T2/T3a/T3b e D-5/D-8) estão fechados. Falta:

| # | Marco | Critério de pronto | Estado |
| --- | --- | --- | --- |
| **M5** | Tipos v2 | T4, T5, T6a e T6c: generalização, classes genéricas, narrowing e exaustividade; traits/constraints pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)) | ✅ **fechado** |
| **M6** | HIR + LLVM vertical | L0–L4 + L2.5 + L5a/L5b: inteiros, controle de fluxo, funções, closures, strings, optionais e classes; I1 verde no corpus anotado | 🟡 em andamento |
| **M7** | Runtime completo | L5–L6: classes, coleções, GC e `for-in`; I1 verde no corpus completo | ⬜ |
| **M8** | Performance | L6–L7: desboxar tipos, monomorfizar, `-O2`, benchmarks e JIT | ⬜ |
| **M9** | Ecossistema | formatter, LSP, docs, CI e playground | ⬜ |

**Regra:** a ordem oficial é a §0. Em resumo: L2.5 antes do L5; ADR de L4 antes do L4;
T7/layouts antes do L6. Se algo mudar a semântica de um nível já compilado, o nível afetado
volta para a fila com caso diferencial. Traits nominais continuam pós-MVP e não bloqueiam
nenhum nível.

**Async (ADR-0037):** a arquitetura (frames materializáveis, GC que enxergue frames
suspensos) é preparada durante o L4/L6; a feature entra **depois do M7**, junto com a
stdlib de I/O, e **antes do M8**. Sem I/O não há o que esperar e a feature não passa no
portão do ADR-0014. Paralelismo/multithread fica em avaliação no
[`IDEIAS.md`](IDEIAS.md) I-7 — não é async.

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

### Generics pós-MVP — adiados (2026-11-13)

Nada aqui será feito por enquanto. Retomar só com dor demonstrada (um caso de uso real) ou
quando T6b/constraints existirem; o desenho está no
[ADR-0040](docs/adr/0040-generics-classes-desenho.md) §"Em aberto".

- [ ] `fn map[U]` — métodos genéricos: a função livre cobre; sem constraints o corpo só usa
      operações universais.
- [ ] `class IntBox(Box[Int])` — herança de instanciação: composição cobre; exige
      substituição em cadeia no checker e aumenta a superfície que o L5/L6 tem que
      reproduzir (I1).
- [ ] `is`/`as Box[Int]` — reificação: exige tipos em runtime (*witnesses*), conflita com o
      erasure e com o tree-walk rodar sem `--check`; o erro explícito atual é o
      comportamento correto.

---


## 11. Decisões em aberto

Só o que ainda não foi decidido. Fechadas: [`docs/decisoes.md`](docs/decisoes.md); pendências de tipo:
[`TIPOS.md`](TIPOS.md).

1. **Generics além de funções:** classes genéricas MVP feitas ([ADR-0040](docs/adr/0040-generics-classes-desenho.md));
   métodos genéricos, herança de `Box[Int]` e `is/as` reificado foram **adiados** (sem dor
   demonstrada; ver §10). Continuam em aberto type application explícita e função genérica
   como valor. Monomorfização já decidida ([ADR-0027](docs/adr/0027-generics-t3b.md)).
   Constraints e traits nominais ficam pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)).
2. **Nome e extensão** definitivos (hoje "PyLox", `.lox`; nomes de trabalho na 1.0).
3. **Stdlib pós-1.0:** `io`, `string`, `collections`, `time` não determinístico;
   transcendentais de `math` fora do I3.
4. **Constraints de generics e traits genéricos:** decisão de traits nominais/defaults já
   registrada ([ADR-0038](docs/adr/0038-traits-nominais.md)); falta desenhar `T: Trait`,
   coerência e o custo na monomorfização. `Result`/`Option` já estão implementados
   ([ADR-0041](docs/adr/0041-enums-match.md)); `type` alias está em
   [ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md).
5. **Contratos e agentes:** `requires`/`ensures`/`invariant`, `--contracts` default e JSON
   schema v1 com `fixes[]` — [`IDEIAS.md`](IDEIAS.md) I-4.
6. **`if`/bloco como expressão:** fora da 1.0; reavaliar depois do L4. `match`/enums já
   entraram ([ADR-0041](docs/adr/0041-enums-match.md)).
7. **Paralelismo (multithread):** em avaliação no [`IDEIAS.md`](IDEIAS.md) I-7; async é
   concorrência single-thread ([ADR-0037](docs/adr/0037-async-direcao.md)), não paralelismo.

Fechadas recentemente: backend em `llvmlite` (ADR-0031), normalização de ternário/
`and`/`or`/`??` e strings do L3, enums/match/`Result` (ADR-0041) e exceções
([ADR-0042](docs/adr/0042-excecoes.md)) (ver [`docs/adr`](docs/adr/) e [`CHANGELOG.md`](CHANGELOG.md)).

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