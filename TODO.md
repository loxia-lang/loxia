# TODO — Roadmap e ideias

Documento vivo do projeto: o que falta no livro, o que quero mudar na linguagem, como
pretendo tipar e como chegar no LLVM.

> **Tipos e números têm documento próprio:** [`TIPOS.md`](TIPOS.md) — catálogo de tipos,
> `Int` vs `Float`, literais, overflow, formatação, mapeamento LLVM e decisões `D-*`.
> **Discussões de design em aberto:** [`IDEIAS.md`](IDEIAS.md) — ex.: `val` vs `var`.

**Legenda:** `P0` agora · `P1` próximo · `P2` depois · `P3` algum dia
**Esforço:** `S` (horas) · `M` (dias) · `L` (semanas) · `XL` (meses)

> Regra de ouro: a linguagem precisa **fechar semanticamente** antes do backend.
> Cada feature nova entra com teste; cada mudança de sintaxe entra documentada aqui.

---

## 0. Agora: base sã e livro concluído

> **M0 concluído** (ver §9): bugs corrigidos, suíte de testes, benchmarks, lint/tipos e CI
> no lugar. **Parte II concluída** (caps. 4–13) e **`val`/`var` decididos e implementados**
> (ADR-0005). Próximo: parâmetros default/campos (I-5), type checker ou sintaxe restante.

### 0.1 Bugs — corrigidos, com regressão na suíte

- [x] **P0-1** imports `from expr` / `from stmt` → `from src.*` (o programa não iniciava).
- [x] **P0-2** `Environment.get`/`assign` procuravam no escopo errado → busca do escopo atual
      para o `enclosing`; blocos, `for` e futuras closures funcionam.
- [x] **P0-3** `!` retornava a truthiness → `not ...`; `!nil` agora é `true`.
- [x] **P0-4** `var a;` usava sentinela `object()` → `None` (imprime `nil`).
- [x] **P1-5** `ErrorReporter.reset()` limpa `had_error`, `had_runtime_error` e `silent`;
      o REPL usa `reset()`.
- [x] **P1-6** `Assign`/`Call`/`Get`/`Logical`/`Set`/`Super`/`This` herdam de `Expr`.
- [x] **P1-7** REPL: `;` final opcional (`1+1;` imprime) via `Parser(repl=True)`.
- [x] **Extra** `AstPrinter` implementa todos os nós (quebrava em `a and b`) e
      `stringify` foi centralizado em `src/values.py`.

Casos de regressão: `block_scope.lox`, `assignment.lox`, `unary.lox`, `variables.lox` e
`errors/*.lox`. Qualquer reintrodução quebra `make test`.

### 0.2 Livro — capítulos 10 a 13 (P0/P1, M)

- [x] **Cap. 10 — Funções**
  - [x] nós `Function`/`Call` (já existiam na AST) + parser
  - [x] `return` via `ReturnSignal` (controle de fluxo interno, como o `Return` do livro)
  - [x] `LoxCallable` (Protocol): `arity()`, `call(interpreter, args)`
  - [x] `LoxFunction` com `environment` de fechamento (closure)
  - [x] `call` na cadeia de precedência (entre `unary` e `primary`)
  - [x] `clock()` nativa
  - [ ] erro de runtime com `stack trace` de frames (o livro só faz no clox; aqui vale a pena)
  - [x] testes: aridade, não-chamável, closure, recursão, ordem de avaliação, `return` no topo
- [x] **Cap. 11 — Resolver**
  - [x] escopo léxico estático, `depth` por variável (`Interpreter.locals`)
  - [x] erros: `Can't read local variable in its own initializer.`,
        `Already a variable with this name in this scope.`
  - [x] `return` fora de função (agora erro de compilação, exit 65)
  - [x] identidade dos nós de AST (`eq=False`) para servir de chave no `locals`
  - [ ] `this` fora de classe (cap. 12)
  - [ ] (bônus) resolver já guarda *slots* em vez de nomes → prepara VM/LLVM
- [x] **Cap. 12 — Classes**
  - [x] `LoxClass`, `LoxInstance`, `Get`/`Set`, `this`, `init`
  - [x] chamada de método e `arity` do construtor (`init` define a aridade)
  - [x] métodos ligados (`bind`) e `this` resolvido pelo resolver
  - [x] erros: `this` fora de classe, `return` com valor em `init`, propriedade inexistente
- [x] **Cap. 13 — Herança**
  - [x] `<`, `super`, método herdado (`find_method` recursivo)
  - [x] `super` ligado ao `this` atual; resolver com escopo próprio de `super`
  - [ ] decisão de sintaxe final (`extends` vs `<`, `super`) — ver §11 ao planejar a
        linguagem própria

### 0.3 Higiene (P1, S)

- [x] `src/__init__.py` e imports previsíveis
- [x] suíte pytest + runner golden (`tests/`)
- [x] benchmarks com baseline (`bench/`)
- [x] ruff + mypy strict + Makefile + CI + skills (`.dsh/skills`)
- [x] [`TIPOS.md`](TIPOS.md): catálogo de tipos e modelo numérico (`Int` vs `Float`)
- [x] `README.md` de verdade: o que é, como rodar, sintaxe atual, roadmap resumido
- [x] documentação em `docs/` (`spec`, `tech`, `adr`) + glossário + teste de links
- [ ] `exemplos/` com 4–5 programas (fib, fizzbuzz, closures, classes, quicksort)
- [ ] `--version` e `--dump-ast` no CLI
- [ ] entrypoint `python -m lox` além de `main.py`
- [ ] remover `disable_error_code = ["abstract"]` do mypy ao terminar o cap. 13

---

## 1. Linguagem: a sintaxe que eu quero

### 1.1 Princípios

1. **Sem ruído** — `;` opcional, chaves opcionais para corpo de uma linha, `elif`.
2. **Expressões primeiro** — quase tudo produz valor; `if`/`match`/bloco são expressões
   (a ser confirmado, §11).
3. **Imutável por padrão** (proposta) — `val` (imutável) e `var` (mutável); parâmetros
   imutáveis. Ainda em aberto: argumentos em [`IDEIAS.md`](IDEIAS.md) I-1.
4. **Tipos opcionais, não ceremony** — `fn soma(a, b) { a + b }` deve funcionar; anotar
   só onde ajuda (`fn fib(n: Int) -> Int`).
5. **Falhar cedo e claro** — erro com linha/coluna, sublinhado e dica.
6. **Previsível** — nada de coerção implícita, nada de `nil` surpresa.

### 1.2 De/para (Lox atual → proposta)

```lox
// hoje
for (var i = 0; i < 10; i = i + 1) { print i; }
fun soma(a, b) { return a + b; }

// proposta
for i in 0..10 { println(i) }
fn soma(a, b) -> a + b            // corpo de expressão, sem return
```

Programa-alvo (mistura tudo o que quero):

```lox
// fib.lox — como eu gostaria que a linguagem fosse em ~1 ano
fn fib(n: Int) -> Int {
  if n < 2 { n } else { fib(n - 1) + fib(n - 2) }
}

fn main() {
  val n = 30
  println("fib(${n}) = ${fib(n)}")          // interpolação

  val pessoas = [Pessoa("Ana", 32), Pessoa("Bia", 28)]

  for p in pessoas {
    val rotulo = p.nome ?? "sem nome"       // fallback de nil
    println("${rotulo} tem ${p.idade} anos")
  }

  val primeiro = pessoas[0]?.endereco?.cidade  // optional chaining
}
```

### 1.3 Checklist de sintaxe

**Estrutural**
- [ ] `P1` **`;` opcional** (inserção por newline). Regras: inserir no fim de linha,
      exceto antes de `)`, `]`, `}`, `,`, `.`, `?.`, e operadores binários/infixos
      (`+ - * / % == != < > <= >= and or ?? |>`) nem antes de `else`/`catch`.
      Consequência: `val x = a\n-b` precisa de cuidado. Lox2 já faz isso — referência.
- [ ] `P1` **`elif`** em vez de `else if`.
- [ ] `P2` **chaves opcionais** para corpo de uma instrução (`if x > 0 print x`).
- [x] `P2` **`val`** imutável + **`var`** mutável (erro em reatribuir `val`) —
      [ADR-0005](docs/adr/0005-val-var-imutabilidade.md); histórico em
      [`IDEIAS.md`](IDEIAS.md) I-1.
- [x] `P2` **parâmetros imutáveis** por padrão; `var` explícito para mutar
      (`fun f(var x)`), mesma decisão.
- [ ] `P2` **corpo de expressão** em `fn` (`fn dobro(x) -> x * 2`).
- [ ] `P2` **bloco como expressão** (último valor do bloco é o valor).
- [ ] `P3` **`match`** estrutural com `=>` e exaustividade quando o tipo for enum/union.
- [ ] `P3` **`loop { }`** infinito e `break`/`continue` com rótulo (`break outer`).

**Operadores e literais**
- [x] `P0` **`%`** (resto truncado, sinal do dividendo; `Int` e `Float`) —
      [ADR-0006](docs/adr/0006-int-float-separados.md).
- [ ] `P2` **`**`** (potência, associativa à direita).
- [ ] `P2` **`//`** divisão inteira? bloqueado: colide com comentário; decidir token
      ([`TIPOS.md`](TIPOS.md) `D-4`).
- [ ] `P2` **ranges** `0..10` (exclusivo) e `0..=10` (inclusivo) — iteráveis.
- [ ] `P2` **ternário** `cond ? a : b` (ou só `if` expressão; decidir).
- [ ] `P2` **`?.`** optional chaining e **`??`** coalescência de nil.
- [ ] `P2` **`?:`** elvis (`a ?: b`) como atalho de `a ?? b`? (evitar duplicar; decidir)
- [ ] `P2` **interpolação** `"${expr}"` no scanner (e escapes `\n`, `\t`, `\"`, `\\`, `\u{...}`).
- [ ] `P2` **strings multilinha** com `"""` e raw strings `r"..."`.
- [ ] `P2` **UTF-8** de verdade em identificadores e strings (hoje o scanner é ASCII puro).
- [ ] `P3` **spread** `...lista` em chamadas e literais.

**Dados e funções**
- [ ] `P2` **arrays** `[1, 2, 3]`, acesso `a[i]`, `push`, `len`.
- [ ] `P2` **mapas** `{ "a": 1 }` — cuidado: `{` de mapa vs bloco. Opções: `#{...}`,
      ou exigir `:`/`,` para desambiguar. Lox2 resolveu? estudar antes.
- [ ] `P2` **`for x in iterável`** + protocolo de iterador (método `iter()`).
- [ ] `P2` **variádicos** `fn log(nivel, ...args)` e `args` como lista. Viabilidade e
      comparação com `**kwargs` em [`IDEIAS.md`](IDEIAS.md) I-5 (complemento): `*args`
      talvez, `**kwargs` não (depende de named args e destrói tipagem).
- [ ] `P2` **lambdas** `fn(x) -> x * 2` e **trailing closure** `lista.map { |x| x * 2 }`
      (a sintaxe de trailing closure é ideia do Lox2/Kotlin/Swift).
- [ ] `P3` **argumentos nomeados** e **defaults** `fn ponto(x, y = 0)`.
- [ ] `P3` **destructuring** `val (a, b) = par` / `val { nome, idade } = pessoa`.

**Módulos e metaprogramação**
- [ ] `P3` **namespaces/imports** (`namespace app.model`, `using app.model.Pessoa`).
      Ideia boa do Lox2; essencial quando existir biblioteca padrão.
- [ ] `P3` **traits/protocolos** (`trait Show { fn show() -> String }` + `with Show`).
- [ ] `P3` **extension methods** (`impl String { fn gritar() }`).
- [ ] `P3` **operator overloading** via métodos mágicos (`__add__`, `__eq__`) — igual Lox2.
- [ ] `P3` **`type` alias** (`type UserId = Int`) e **`as`** cast explícito.
- [ ] `P3` **`derive`** de `show`/`eq`/`hash` para classes simples.

**Erros**
- [ ] `P2` **`throw` / `try` / `catch` / `finally`** com stack trace. Alternativa mais
      simples primeiro: `Result<T, E>` como tipo. Exceções em LLVM são caras (§6.7).
- [ ] `P2` **`assert`** e **`panic`** como funções nativas.
- [ ] `P3` **erros como valores** (`Result`/`Option`) para código que compila puro.

### 1.4 Decisões de sintaxe já descartadas (para não revisitar)

- `end` no estilo Ruby/Lua → **não**: chaves são melhores para erro de parser.
- Off-side rule (indentação significativa) → **não**: caro no scanner e ruim no REPL.
- `print` como statement? fica, **mas** `println`/`print` como funções também (Lox2 fez
  isso e simplifica a stdlib). Ver §11.
- Herança com `<` → provavelmente `extends` (mais legível, e libera `<` só para comparação).
- Pipeline `|>` / `:>` → **não** por enquanto (decisão de 2026-11-11): mais um operador e
  nível de precedência, convenção invisível da posição do argumento e acoplamento com
  `print`-função/stdlib, sem caso de uso urgente antes de `List`. Histórico e gatilhos de
  reabertura em [`IDEIAS.md`](IDEIAS.md) I-2.

---

## 2. Sistema de tipos com inferência

> **Catálogo de tipos e modelo numérico:** [`TIPOS.md`](TIPOS.md) — o que existe, como
> `Int`/`Float` se comportam, decisões abertas (`D-1`…) e roadmap de números.
> Esta seção cobre **como implementar** a inferência.

### 2.1 Objetivo

Tipagem **estática opcional**, com anotações onde importam:

```lox
fn soma(a: Int, b: Int) -> Int { a + b }
soma(1, 2)        // ok
soma("a", 2)      // erro em tempo de compilação:
                  //   expected Int, found String
                  //   --> linha 1, coluna 6
```

E inferência na fronteira:

```lox
fn soma(a, b) { a + b }   // 'a: T, 'b: T -> T
val x = soma(1, 2)        // T := Int; x: Int
val y = soma(1, "b")      // erro: T := Int e T := String não unificam
```

O ponto central: **o argumento é checado contra o parâmetro**, e o parâmetro sem anotação
vira uma variável de tipo unificada. Isso pega 90% dos erros bobos sem exigir anotação.

### 2.2 Estratégia (não fazer HM completo de cara)

Hindley–Milner puro é incompatível com o que a linguagem já tem/quere: mutação
(`var`), `nil`, subclasses e métodos. O caminho realista é **bidirecional + unificação
nas chamadas**, em camadas:

| Etapa | O que faz | Ganho |
| --- | --- | --- |
| **T1** | `Ty` no AST, parser aceita `: Tipo` e `-> Tipo`; checker só valida o que está anotado, resto é `Any` | sintaxe pronta, zero falso positivo |
| **T2** | inferência local: `val x = 1` → `Int`; `fn f() -> 1` → `Int`; checagem de `return` | erros óbvios |
| **T3** | parâmetro sem anotação vira `TyVar`; unificar a cada chamada **no arquivo** | o "check nos args" que eu quero |
| **T4** | generalização (let-polymorphism) → funções genéricas implícitas; `fn id<T>(x: T) -> T` explícito | bibliotecas |
| **T5** | uniões `Int \| String`, opcionais `T?`, narrowing em `if x != nil` | expressividade |
| **T6** | traits/protocolos estruturais, checagem de exaustividade no `match` | abstração |
| **T7** | erase (tipos só vivem em compile-time) e integração com o codegen | backend sabe layouts |

### 2.3 Modelo de tipos

```
Ty = Any | Nil | Bool | Int | Float | String
   | List[T] | Map[K, V] | Tuple[T...]
   | Fn[params..., ret]           # fn(Int, String) -> Bool
   | Class(name, args...)         # instância
   | ClassType(name)              # a classe como valor
   | Union[A, B, ...]
   | TyVar(id)                    # variável de unificação
   | Never                        # bottom: throw/return
```

- `Any` é a válvula de escape: desliga checagem naquele ponto (e no LLVM vira valor boxeado).
- `Never` faz `throw`/`return` não estragarem o fluxo de tipos.
- Guardar em `src/types.py` (novo), com `__eq__`/`__hash__` para unificação rápida.

### 2.4 Unificação (núcleo)

```python
def unify(a: Ty, b: Ty) -> None:
    a, b = resolve(a), resolve(b)
    if a == b: return
    if isinstance(a, TyVar): a.bind(b); return
    if isinstance(b, TyVar): b.bind(a); return
    if isinstance(a, Fn) and isinstance(b, Fn):
        if len(a.params) != len(b.params): raise TypeError(...)
        for pa, pb in zip(a.params, b.params): unify(pa, pb)
        unify(a.ret, b.ret); return
    if isinstance(a, List) and isinstance(b, List): unify(a.elem, b.elem); return
    if a is Any or b is Any: return          # escape hatch
    raise TypeError(f"expected {b}, found {a}")
```

Detalhes que mordem:
- **occurs check** (`T = List[T]`) → erro claro, senão loop infinito.
- **níveis/escopo de generalização** (estilo `let`), senão `fn id(x) { x }` vira
  monomórfico e contamina o arquivo.
- **value restriction**: generalizar tudo que é mutável dá unsoundness; generalizar só
  funções/valores imutáveis.
- unificação **mutável** (`var x = nil; x = 1`) pede união ou `Any` — decidir em §11.
- **mensagens de erro**: sempre apontar o `Token`/span, nunca só "type mismatch".

### 2.5 Checagem de chamada (o caso que mais importa)

```
infer(Call(callee, args)):
    f = infer(callee)
    if not isinstance(f, Fn): erro "não é função"
    if len(args) != len(f.params): erro de aridade (com dica: "f espera 2, veio 3")
    for arg, param in zip(args, f.params):
        check(arg, param)      # bidirectional: empurra o tipo esperado pra baixo
    return f.ret
```

`check(expr, expected)` desce empurrando o tipo: literal numérico em contexto `Float`
vira `Float`; lista vazia `[]` em `List[Int]` funciona. `infer(expr)` sobe sintetizando.
Essa assimetria é o que faz a inferência parecer "mágica" sem ser HM.

### 2.6 Onde plugar no pipeline

```
Scanner → Parser → Resolver (escopos/depth) → TypeChecker → Interpreter
                                                     │
                                                     └→ (futuro) HIR → LLVM
```

- O checker roda **depois** do resolver (precisa de escopo e `depth`).
- `--check` no CLI: só checa, não executa (útil em CI e editor).
- O interpretador continua dinâmico; tipos são apagados em runtime (como o Lox2).
  Isso permite `Any` e mantém o tree-walk como oráculo dos testes diferenciais.
- Anotação errada é **erro**, não warning. `Any` é o opt-out explícito.

### 2.7 Extras que valem o esforço

- [ ] `P2` **narrowing**: `if x != nil { x.metodo() }`, `if x is Pessoa { ... }`.
- [ ] `P2` **exhaustividade** em `match`/enum.
- [ ] `P3` **flow-sensitive** para `val` (uma atribuição só).
- [ ] `P3` **tipos de função** como valores de primeira classe (essencial p/ lambdas).
- [ ] `P3` **generics com constraints** (`T with Show`).
- [ ] `P3` **inferência de retorno** para funções com corpo de expressão.
- [ ] `P3` **LSP**: `--check --json` com spans para o editor sublinhar.

### 2.8 Referências de design

- **Lox2**: tipagem opcional, `T?`, uniões, generics, `type` alias, erase em runtime.
  É a maior referência prática aqui (mesmo tendo ido para VM em C).
- **Kotlin/Swift**: nullability explícita, smart casts, trailing closures.
- **TypeScript**: `Any` como escape e "structural typing" — bom modelo mental para traits.
- **HM clássico** (OCaml): inspiração para unificação/generalização, mas não copiar.

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
- [ ] `P2` **`try/catch/finally`** se a decisão for exceções (§1.3).
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

- [x] `P1` **harness de benchmark** (`bench/run.py`) com baseline versionado e gate de
      regressão (`make bench`). Casos: `loop_sum`, `nested_loop`, `branchy`,
      `string_concat`.
- [ ] `P2` resolver já com **slots** (índice inteiro) em vez de dict de nomes.
      É o maior ganho por linha de código no tree-walk.
- [ ] `P2` `Environment` com lista + profundidade em vez de dict encadeado.
- [ ] `P3` inline caching de `Get`/métodos.
- [ ] `P3` novos casos quando a linguagem crescer: `fib` recursivo (cap. 10), criação de
      objetos/`Get` (cap. 12), `List`/`Map` (sintaxe nova).
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

- [x] `P1` **pytest** + `tests/cases/*.lox` no formato do livro
      (`// expect:`, `// expect runtime error:`), com runner próprio
      (`tests/runner.py`, roda também fora do pytest). 71 testes hoje.
- [x] `P1` **ruff** (`check`) e **mypy strict** configurados no `pyproject.toml`
      (`make lint`, `make type`).
- [x] `P1` **skills de projeto** em `.dsh/skills/` (`lox-feature`, `lox-testing`,
      `lox-bench`, `lox-debug`) — procedimentos carregáveis por tarefa.
- [ ] `P1` **pre-commit** rodando ruff/mypy/pytest.
- [x] `P1` **CI** (GitHub Actions): `uv sync`, ruff, mypy, pytest.
- [x] `P1` **`Makefile`**: `run`, `test`, `case`, `lint`, `type`, `fmt`, `check`, `bench`,
      `baseline`.
- [ ] `P2` **importar a suíte oficial** do craftinginterpreters como casos extras
      (adaptando o formato de expectativa); ótimo para validar o cap. 10–13.
- [ ] `P2` **testes diferenciais** interpretador × LLVM (mesmo stdout, exit code).
- [ ] `P3` **fuzzing** do scanner/parser com `hypothesis`: "nunca crashar, nunca loopar".
- [ ] `P3` **snapshot de AST** em arquivo (hoje o `AstPrinter` é usado em testes pontuais).
- [ ] `P3` **tree-sitter grammar** → highlight no Neovim/VS Code.
- [ ] `P3` **LSP** mínimo (diagnostics + hover de tipo) — depois do checker.
- [ ] `P2` **CLI agent-friendly**: `--json` em `check`/`ast`/`types`/`fmt`, `--no-progress`,
      `--timeout`, sem prompt interativo, exit codes estáveis (checklist em
      [`IDEIAS.md`](IDEIAS.md) I-4).
- [ ] `P3` **`lox fmt`** e teste de idempotência (formatar duas vezes = igual).
- [x] `P1` **estrutura de docs**: `docs/spec` (comportamento atual), `docs/tech`
      (arquitetura), `docs/adr` (decisões) e glossário; links verificados por
      `tests/test_docs_links.py`.
- [ ] `P3` **site publicado** (mkdocs/mdbook) gerado a partir de `docs/`.

---

## 8. Ideias do Lox2 que valem (e as que não valem)

Contexto: o Lox2 é um **superset de Lox em C** com VM de bytecode, tipagem estática
opcional, namespaces, exceções, async e JIT — caminho bem diferente do meu (Python +
tree-walk + LLVM). Mas várias **features de linguagem** são ótimas referências.

| Recurso do Lox2 | Vale? | Esforço | Nota |
| --- | --- | --- | --- |
| `;` inferido por newline | ✅ | M | melhora muito a fluidez; cuidado com `else`/operadores |
| tipagem estática opcional + erase | ✅ | L | é exatamente o meu §2 |
| arrays e dicionários literais | ✅ | M | básico de qualquer linguagem útil |
| `?.`, `??`, `?:` | ✅ | S | alto ganho, baixo custo |
| `%` e ranges `..` | ✅ | S | ranges viabilizam `for i in 0..10` |
| interpolação de string | ✅ | S | ergonomia enorme |
| UTF-8 em strings e identificadores | ✅ | M | hoje o scanner é ASCII |
| `for x in` + iterator protocol | ✅ | M | substitui o `for` C-style |
| parâmetros imutáveis por padrão | ✅ | S | combina com `val` |
| `let` (`val` no Lox2) imutável | ✅ | S | imutável por padrão |
| `extends` em vez de `<` | ✅ | S | mais legível |
| `print` como função (`println`) | ✅ | S | simplifica a stdlib |
| variádicos `...args` | ✅ | S | fácil e útil |
| lambdas anônimas | ✅ | M | precisa de closures (cap. 10) |
| trailing closure | ✅ | M | ergonomia p/ `map`/`filter` |
| `type` alias | ✅ | S | útil com generics |
| generics + constraints | ⏳ | XL | só depois de T4 (§2) |
| uniões `Int \| String` | ⏳ | L | depende do checker |
| traits + `with` | ⏳ | L | ótimo para composição; depois de classes |
| operator overloading | ⏳ | M | divertido e barato depois de classes |
| namespaces/import | ⏳ | L | necessário quando houver stdlib |
| `throw`/`try`/`catch`/`finally` | ⏳ | L | ótimo na VM; caro no LLVM (§6.7) |
| `match` estrutural | ⏳ | L | depois de uniões/enums |
| `as` cast | ⏳ | S | junto com o checker |
| extension methods | ⏳ | M | depois de traits |
| separar `Int` de `Float` | ✅ | M | feito no tree-walk (ADR-0006); falta refletir no LLVM |
| campos declarados fora do `init` | 🤔 | S | bom p/ tipagem; decidir junto com classes |
| classes como valores / metaclasses | 🤔 | L | poderoso, mas confunde; só se precisar |
| interceptors (`get`/`set` mágicos) | ❌ | L | mágica demais para o meu gosto |
| `Object` raiz / tudo é objeto | ❌ | L | simplifica o Lox2, mas custa no codegen |
| generators/`yield` | ❌ | XL | precisa de corrotinas; ótimo, mas fora de escopo |
| `async`/`await` + event loop | ❌ | XL | projeto inteiro; não é o objetivo |
| JIT tracing / SSA / CFG | ❌ | XL | o LLVM já faz otimização por mim |
| GC geracional, shapes, inline cache | ❌ | XL | otimizações de VM que não vou ter |
| cache de bytecode `.loxo` | ❌ | M | substituído por cache de `.o`/IR |
| FFI com C | ⏳ | L | legal, mas depois de linking estável |
| biblioteca padrão (lang/util/io/net) | ⏳ | L | mínima primeiro (`math`, `io`, `string`) |

**O que eu levo de mais valioso do Lox2:** a lista acima + o *design* de tipos opcionais
com erasure + a ideia de `for-in` com iterator protocol + a disciplina de semicolon
inference. **O que eu ignoro:** a VM, o GC geracional, o async e o JIT — porque o LLVM
cobre a parte de geração de código e eu quero manter o escopo humano.

---

## 9. Milestones (ordem sugerida)

| # | Marco | Critério de pronto |
| --- | --- | --- |
| **M0** ✅ | Base sã | bugs P0/P1 corrigidos, suíte pytest verde (71), benchmark com baseline, lint/tipos/CI |
| **M1** ✅ | Livro, metade 2 | funções, closures, resolver, classes, herança (caps. 10–13) |
| **M2** | Linguagem estável | suíte oficial do livro passando + exemplos + README |
| **M3** | Sintaxe nova | `;` opcional, `val`/`var` ✅, `fn`, interpolação, arrays, `for-in`, `?.`/`??` |
| **M4** | Tipos v1 | T1–T3: anotações, inferência local, checagem nos args, `--check` |
| **M5** | Tipos v2 | T4–T6: generics, uniões/opcionais, traits, narrowing, exaustividade |
| **M6** | HIR + LLVM MVP | L0–L2: inteiros, controle de fluxo, funções, binário nativo |
| **M7** | Runtime completo | L3–L5: strings, closures, classes, GC (Boehm) |
| **M8** | Performance | L6–L7: desboxar tipos, monomorfizar, `-O2`, benchmarks, JIT |
| **M9** | Ecossistema | formatter, LSP, docs, CI, playground |

Regra: **M3 só começa com M2 verde**, e **M6 só com M4 verde**. Sem isso, o codegen
persegue uma linguagem que ainda muda.

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
- [ ] **`lox doc`** — gera docs a partir de comentários `///`.
- [ ] **Modo "strict"** vs "loose" para compatibilidade com Lox puro durante a transição.

---

## 11. Decisões em aberto

Registrar a decisão aqui **antes** de implementar, para não refatorar duas vezes.
Decisões **numéricas e de tipos** (`Int`/`Float`, literais, overflow, formatação,
nullability, `1 == 1.0`…) ficam em [`TIPOS.md`](TIPOS.md) §11, com id `D-n`.

1. **Nome e extensão** da linguagem (hoje "PyLox", arquivos `.lox`).
2. **`val`/`var`** — **decidido**: `val` imutável (exige inicializador) e `var` mutável;
   parâmetros `val` por padrão. Ver [ADR-0005](docs/adr/0005-val-var-imutabilidade.md).
   Campos e defaults ficam em [`IDEIAS.md`](IDEIAS.md) I-5.
3. **`Int` vs `Float`** — **decidido**: tipos separados, `Int` = i64 e `Float` = f64, com
   promoção só `Int → Float`; implementado no tree-walk. Ver
   [ADR-0006](docs/adr/0006-int-float-separados.md) e [`TIPOS.md`](TIPOS.md) §3.
4. **Nullability**: `T?` explícito (Kotlin) ou tudo anulável (Lox atual)?
5. **Blocos/`if` como expressão**: último valor implícito ou `return` obrigatório?
   (afeta legibilidade e o parser)
6. **`print`**: statement (livro) ou função `println` (Lox2)? Ou ambos?
7. **`match`**: antes ou depois do codegen? (antes facilita enums; depois é mais seguro)
8. **Classes**: manter herança simples ou trocar por `struct` + traits/composição?
9. **Exceções**: `throw/try` na linguagem ou `Result`? (LLVM pesa contra exceções)
10. **Generics**: monomorfização (perf) ou erasure (simplicidade)? (tende a mono)
11. **Módulos**: namespaces hierárquicos (Lox2) ou arquivos = módulos (Python/Go)?
12. **Backend**: `llvmlite` desde o começo ou `.ll` textual + clang primeiro?
13. **Escopo da stdlib**: `math`, `io`, `string` e `collections` bastam no início?
14. **Pipeline** — **decidido (rejeitado) em 2026-11-11**: sem operador `|>`/`:>` por
    enquanto. Argumentos, alternativas e gatilhos de reabertura em
    [`IDEIAS.md`](IDEIAS.md) I-2.
15. **Stdlib**: builtins globais (`len`, `println`) ou métodos/extensões? Conversão
    namespaced (`Int.parse`) vs `int()` sobrecarregado? Ver [`IDEIAS.md`](IDEIAS.md) I-3.
16. **Contratos e agentes**: `requires`/`ensures`/`invariant` opcionais? `--contracts`
    default? JSON schema v1 com `fixes[]`? Ver [`IDEIAS.md`](IDEIAS.md) I-4.

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
