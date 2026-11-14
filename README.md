# PyLox 1.0.0

Interpretador da linguagem **Lox** em Python, construído seguindo *Crafting Interpreters*
(Parte II — jlox), com o objetivo de evoluir para uma linguagem própria e um backend
**LLVM**.

- ✅ Parte II concluída: scanner, parser, resolver, funções/closures, classes e herança.
- ✅ Sintaxe própria: `fn`, `elif`, `;` opcional, `val`/`var`, campos declarados e `--check`.
- ✅ Expressões: ternário `a if c else b`, `??`, `?.`, negação `not`, interpolação
  `"${expr}"`, escapes, string multilinha `"""..."""` e raw `r"..."`.
- ✅ Narrowing de `T?`: `if (x != nil)`, `if (x == nil)`/early return e truthiness no `--check`.
- ✅ `x is T`: primitivos, classes/subclasses, `List[T]`/`Map[K, V]` e uniões; narrowing em
  `if`/`else`, `while` e `and`/`or`.
- ✅ Listas tipadas `List[T]`: literal, indexação, `push`/`pop`, `len` e `for-in`.
- ✅ Mapas tipados `Map[K, V]`: literal `{ "a": 1 }`, `get`/`has`/`remove`/`keys`/`values`,
  igualdade estrutural e `for-in` de chaves.
- ✅ API híbrida: `len`/`str`/`repr` globais e métodos específicos de lista/mapa.
- ✅ Tipos de função nas anotações: `fn(Int) -> Int`, callbacks, variância e classe como
  construtor.
- ✅ Lambdas `fn(x) => ...` e `fn(x) { ... }`, com tipagem contextual e retorno inferido.
- ✅ Funções genéricas `fn id[T] (x: T) -> T`, `map`/`filter`, inferência na chamada e
  monomorfização planejada no backend ([ADR-0027](docs/adr/0027-generics-t3b.md)).
- ✅ Casts explícitos com `as`, `Int.parse`/`Float.parse` → `T?` e `math.*` determinístico
  ([ADR-0029](docs/adr/0029-conversoes-math.md)).
- ✅ Overflow checado com `--debug`; release continua wrapping
  ([ADR-0028](docs/adr/0028-overflow-debug.md)).
- ✅ Checker valida retorno em todos os caminhos, inicialização de campos e override
  compatível.
- 🧪 Suíte pytest com golden cases `.lox`, testes unitários e benchmarks com baseline.
- 🌍 Suíte oficial do Crafting Interpreters (caps. 10–13) adaptada em `tests/official/`.
- 🏷️ **Versão 1.0.0**: release local da linguagem no tree-walk; backend nativo é
  pós-1.0. Ver [`CHANGELOG.md`](CHANGELOG.md).
- 🧊 **Escopo da 1.0 congelado** ([ADR-0026](docs/adr/0026-freeze-1.0.md), com T3b e D-8
  como exceções): erros de runtime fatais, `clock` removido do prelúdio, strings UTF-8
  com identificadores ASCII, `print` como statement e escopo single-file. O mapa
  **1.0 × pós-1.0** está em [`ESCOPO.md`](ESCOPO.md).
- 📐 Próximo passo: **L7b** (revisão das mensagens de erro de codegen; `-O2` e benchmark
  nativo já entregues). Kernel v1 em andamento (13.3/13.4 prontos); JIT no REPL fica como
  pendência futura. O L5, o T7 e o L6a–L6k já
  entregaram classes,
  herança, closures, `is`/`as`, optionais escalares, `Range`/`for-in`, listas, mapas,
  tuplas, `Any`, `math`/parse e defaults como valor; traits e constraints ficam
  pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)).

## O que esta linguagem promete

A identidade não é o catálogo de features (todas são emprestadas, e isso é normal) — é o
que se promete e se verifica em CI ([ADR-0014](docs/adr/0014-identidade-e-invariantes.md)):

- **I1 — o interpretador é a especificação.** O mesmo programa, interpretado e compilado,
  dá o mesmo stdout, stderr e exit code, byte a byte, para o corpus declarado por nível
  (hoje L0–L6 em `tests/test_backend.py`).
- **I2 — nada acontece implicitamente.** Sem coerção entre `Int`/`Float`/`String`, sem
  truthiness exótica, sem `nil` surpresa.
- **I3 — determinismo observável.** Mesma entrada ⇒ mesmos bytes de saída e de
  diagnóstico: sem endereço, timestamp, PID ou caminho absoluto.
- **I4 — `--check` limpo compila.** Se o checker aceita, o binário compila; a única recusa
  aceitável é a lacuna declarada (`... is not supported by the backend yet.`). O checker é
  a fonte única dos tipos.
- **Memória é contrato.** O binário usa GC Boehm ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)):
  hard cap de 128 MiB e I1 até 64 MiB de memória viva; estourar é `exit 70` +
  `Out of memory.`. O interpretador não tem teto — o I1 vale dentro do orçamento.

Detalhes e o que **não** é prometido: [`docs/spec/garantias.md`](docs/spec/garantias.md).

## Rodar

Requisitos: Python 3.13 e [`uv`](https://docs.astral.sh/uv/). O backend nativo (`--emit`)
pede `llvmlite` (`uv sync --extra llvm`), um compilador C e, para `--emit=exe`, a `libgc`
(Boehm; `libgc-dev` no Debian/Ubuntu, `bdw-gc` no Homebrew). O interpretador não precisa de
nada disso.

```bash
uv run main.py                 # REPL (Ctrl+C/Ctrl+D para sair)
uv run main.py programa.lox    # executa um arquivo
uv run python -m lox           # mesma coisa, via pacote
uv run main.py --version       # pylox 1.0.0
uv run main.py --dump-ast prog.lox   # imprime a AST (S-expression), não executa
uv run main.py --check prog.lox      # checa os tipos, não executa
uv run main.py --debug prog.lox      # checa overflow de Int em runtime (release faz wrap)
uv sync --extra llvm                 # habilita o backend nativo (llvmlite)
uv run main.py --emit=ll prog.lox    # IR do LLVM (inspeção)
uv run main.py --emit=obj prog.lox   # .o para linkar
uv run main.py --emit=exe -o app prog.lox   # binário nativo
uv run main.py --emit=ll --output prog.ll prog.lox  # IR em arquivo (--output)
make test                      # pytest
make check                     # ruff + mypy strict + pytest
make hooks                     # instala o hook de pre-commit
make bench                     # benchmarks do interpretador vs baseline
make bench-native              # benchmarks do binário nativo (speedup vs baseline)
# resultados e metodologia: bench/README.md
```

Exit codes do CLI: `65` erro de compilação, `70` erro de runtime, `66` arquivo ausente,
`2` uso inválido (ex.: `--dump-ast` sem script). O binário gerado por `--emit=exe` segue o
mesmo contrato: `0` no sucesso e `70` no erro de runtime, com o mesmo stderr.

### Diagnósticos

Diagnósticos de compilação vão para stderr no formato
`arquivo:linha:col: error[CODIGO]: mensagem` + trecho com caret; erros de runtime usam o
mesmo cabeçalho, sem caret. O formato é determinístico (caminho relativo ao CWD, ordem
fixa, sem timestamp/endereço) e os códigos são estáveis — catálogo em
[`docs/spec/erros.md`](docs/spec/erros.md).

```bash
uv run main.py --check --error-format=short prog.lox  # uma linha por diagnóstico
uv run main.py --check --error-format=json prog.lox   # envelope JSON v1 (stdout)
uv run main.py --error-format=json prog.lox           # diagnósticos JSON (stderr)
uv run main.py --color=never prog.lox                 # sem ANSI (também respeita NO_COLOR)
uv run main.py --max-errors=5 prog.lox                # limita (0 = sem limite)
```

`--error-format=human` (padrão) mostra o trecho; `short` é o cabeçalho; `json` traz
`schema_version`, `code`, `phase`, `span` (linha/coluna em code points e `offset` em bytes)
e `summary`. Em `--check` o JSON vai para **stdout**; em `run`/`build` vai para **stderr**
(o programa/IR já usam stdout). `--color` aceita `auto|always|never` e `NO_COLOR` desliga
a cor no modo `auto`.

O backend nativo cobre **L0–L6**: `Int`/`Float`/`Bool`/`nil`/`String`, optionais escalares (`Int?`/`Float?`/`Bool?`), `if`/`while`,
variáveis, funções com recursão, ternário/`and`/`or`/`??`, concatenação, interpolação,
`len`/`str`/`repr`, funções locais/lambdas, closures (células e `env`), valores de
função (`<fn f>`/`<lambda>`), classes/campos/métodos/herança, monomorfização de funções e
classes genéricas, containers, `Any`, tuplas, enums e exceções. O que resta é qualidade de
L7 (passes/benchmarks); o backend sem representação falha com erro explícito, nunca com
lowering silencioso. Contratos em
[`docs/adr/0031-backend-nativo.md`](docs/adr/0031-backend-nativo.md),
[`docs/adr/0046-closures-celulas-l4.md`](docs/adr/0046-closures-celulas-l4.md) e
[`docs/adr/0074-gc-boehm-e-contrato-de-memoria.md`](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md).

## Exemplo

```lox
class Conta {
  var saldo;

  init(saldo) {
    this.saldo = saldo;
  }

  deposita(valor) {
    this.saldo = this.saldo + valor;
  }
}

var c = Conta(10);
c.deposita(5);
print c.saldo;  # 15
```

## Tipos

Funções anotadas e inferência nos locais; o checker é opt-in (`--check`) e os tipos são
apagados em runtime. `;` é opcional no fim da linha e `elif` substitui `else if`:

```lox
fn soma(a: Int, b: Int) -> Int {
  return a + b
}

val total = soma(1, 2)      # Int inferido
val talvez: String? = nil   # String | Nil

val xs: List[Int] = [3, 1, 2]
xs.push(4)
print len(xs)               # 4
print xs[0]                 # 3
for x in xs { print x }

val idades: Map[String, Int] = {"Ana": 32}
print idades["Ana"]          # 32
print idades.get("Bia") ?? 0 # 0 (get devolve Int?)
idades["Bia"] = 28
for nome in idades { print nome }   # chaves, em ordem de inserção

val saudacao: String? = "Ana"
if (saudacao != nil) {
  print "Oi, ${saudacao}!"   # narrowing: saudacao é String aqui
}
```

Conversões são explícitas: `3.9 as Int`, `Int.parse("42")` (devolve `Int?`) e
`math.floor(3.9)`; não há coerção implícita nem `42.toString()` (use `str(42)`).

Listas e mapas são **homogêneos** e **invariantes**: `List[Int]` não é `List[Float]`, e
`[1, "a"]` é erro no `--check` (a heterogeneidade exige `List[Int | String]` ou
`List[Any]`). Mapas aceitam chaves `String`, `Int` e `Bool`; `m["ausente"]` é erro e
`m.get("ausente")` devolve `nil`. `val` congela o binding, não o conteúdo: `xs.push(4)` e
`idades["Bia"] = 28` são permitidos.

Aritmética inclui `//` (divisão inteira), `**` (potência) e bits
`& | ^ ~ << >> >>>`; comentários usam `#` e `/* */` (aninhado).

```lox
val rotulo = nome ?? "sem nome"          # default só para nil
val cidade = pessoa?.endereco?.cidade    # acesso seguro
val status = "adulto" if idade >= 18 else "menor"
print "linha 1\nlinha 2"                 # escapes
print """texto em
duas linhas"""                          # string multilinha (aspas livres)
print r"c:\temp\novo"                   # raw: `\` literal, sem interpolação
if (not pessoa?.nome) print "sem nome"   # `not` no lugar de `!`
```

## Estrutura

```
main.py          entrypoint compatível (delega para lox/cli.py)
lox/             pacote do CLI: `python -m lox`, --version, --dump-ast
src/             núcleo em pacotes por fase
src/frontend/    lexing, AST, parser, tipos de anotação e ast_printer
src/semantics/   resolver de escopos e checker gradual
src/execution/   valores, ambiente, objetos, nativos e interpreter
src/diagnostics/ erros e ErrorReporter
src/backend/     backend LLVM (llvm_ir isolando a lib, lowering, driver de build)
runtime/         runtime C do código gerado (print, panic, casos de borda de // e %)
exemplos/        programas de exemplo (fib, fizzbuzz, closures, classes, primos, quicksort)
tests/           pytest + golden cases (.lox)
tests/official/  suíte oficial do livro (caps. 10–13), adaptada
bench/           harness de performance e baseline
docs/            especificação, arquitetura e ADRs
TODO.md          roadmap e decisões em aberto
TIPOS.md         pendências de tipos
IDEIAS.md        discussões de design (parking lot)
```

`AGENTS.md` é local (não versionado), com regras de contribuição para agentes/devs.

A suíte oficial do livro roda com:

```bash
uv run pytest tests/test_official_suite.py -q
```

Ela é mantida separada dos golden cases; detalhes de adaptação e `xfail` em
[`tests/official/README.md`](tests/official/README.md).

## Documentação

- **Especificação atual**: [`docs/spec/`](docs/spec/) — [garantias](docs/spec/garantias.md),
  [léxico](docs/spec/lexico.md), [sintaxe](docs/spec/sintaxe.md),
  [semântica](docs/spec/semantica.md), [erros](docs/spec/erros.md).
- **Documentação técnica**: [`docs/tech/arquitetura.md`](docs/tech/arquitetura.md).
- **Decisões de design (ADRs)**: [`docs/adr/`](docs/adr/).
- **Roadmap**: [`TODO.md`](TODO.md) · **tipos**: [`TIPOS.md`](TIPOS.md) ·
  **ideias**: [`IDEIAS.md`](IDEIAS.md).

> A especificação descreve o que o código faz **hoje** (Lox do livro + `val`/`var`,
> `Int`/`Float`, ranges/`for-in`, listas, mapas, tuplas, herança `class B(A)`,
> defaults/campos, checker `--check`, `fn`/`elif`/`;` opcional, ternário/`??`/`?.`,
> `not`, escapes, `"""`/raw, narrowing e generics). O que falta — o resto do L6/L7 no
> backend (enums/`match`, exceções), `break`/`continue`, spread/variádicos e imports — está
> nos documentos de roadmap e ainda **não** está implementado.
