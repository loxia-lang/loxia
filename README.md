# PyLox 1.0.0

Interpretador da linguagem **Lox** em Python, construído seguindo *Crafting Interpreters*
(Parte II — jlox), com o objetivo de evoluir para uma linguagem própria e um backend
**LLVM**.

- ✅ Parte II concluída: scanner, parser, resolver, funções/closures, classes e herança.
- ✅ Sintaxe própria: `fn`, `elif`, `;` opcional, `val`/`var`, campos declarados e `--check`.
- ✅ Expressões: ternário `a if c else b`, `??`, `?.`, interpolação `"${expr}"` e escapes.
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
- 📐 Próximo passo: **M5 (tipos v2)** — generalização, generics de classe/método,
  narrowing completo e exaustividade (TODO §9); traits e constraints ficam pós-MVP
  ([ADR-0038](docs/adr/0038-traits-nominais.md)). O codegen está em
  L0–L3 e fica pausado no L4 até o M5 fechar; tuplas foram implementadas no
  interpretador/checker ([ADR-0036](docs/adr/0036-tuplas-implementacao.md)) e ficam para o
  L6 no backend. T3a (assinaturas + recursão
  mútua), tipos de função, lambdas, T3b e D-8 já estão feitos
  (ADR-0020/0021/0022/0027/0029).

## O que esta linguagem promete

A identidade não é o catálogo de features (todas são emprestadas, e isso é normal) — é o
que se promete e se verifica em CI ([ADR-0014](docs/adr/0014-identidade-e-invariantes.md)):

- **I1 — o interpretador é a especificação.** O mesmo programa, interpretado e compilado,
  dá o mesmo stdout e o mesmo exit code, byte a byte (hoje já vale para execuções
  repetidas; passa a valer entre motores quando o backend LLVM existir).
- **I2 — nada acontece implicitamente.** Sem coerção entre `Int`/`Float`/`String`, sem
  truthiness exótica, sem `nil` surpresa.
- **I3 — determinismo observável.** Mesma entrada ⇒ mesmos bytes de saída e de
  diagnóstico: sem endereço, timestamp, PID ou caminho absoluto.

Detalhes e o que **não** é prometido: [`docs/spec/garantias.md`](docs/spec/garantias.md).

## Rodar

Requisitos: Python 3.13 e [`uv`](https://docs.astral.sh/uv/).

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
make test                      # pytest
make check                     # ruff + mypy strict + pytest
make hooks                     # instala o hook de pre-commit
make bench                     # benchmarks vs baseline
```

Exit codes do CLI: `65` erro de compilação, `70` erro de runtime, `66` arquivo ausente,
`2` uso inválido (ex.: `--dump-ast` sem script). O binário gerado por `--emit=exe` segue o
mesmo contrato: `0` no sucesso e `70` no erro de runtime, com o mesmo stderr.

O backend nativo cobre **L0–L3**: `Int`/`Float`/`Bool`/`nil`/`String`, `if`/`while`,
variáveis, funções de topo com recursão, ternário/`and`/`or`/`??`, concatenação,
interpolação, `len`/`str`/`repr` e arena. O que falta (listas, classes, closures) falha
com erro explícito, nunca com lowering silencioso.
Contrato completo em [`docs/adr/0031-backend-nativo.md`](docs/adr/0031-backend-nativo.md).

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
> `Int`/`Float`, ranges/`for-in`, listas, mapas, herança `class B(A)`, defaults/campos,
> checker `--check`, `fn`/`elif`/`;` opcional, ternário/`??`/`?.` e escapes). O que falta —
> narrowing/generics, interpolação, conversões da stdlib e o backend LLVM — está nos
> documentos de roadmap e ainda **não** está implementado.
