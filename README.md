# PyLox

Interpretador da linguagem **Lox** em Python, construído seguindo *Crafting Interpreters*
(Parte II — jlox), com o objetivo de evoluir para uma linguagem própria e um backend
**LLVM**.

- ✅ Parte II concluída: scanner, parser, resolver, funções/closures, classes e herança.
- ✅ Sintaxe própria: `fn`, `elif`, `;` opcional, `val`/`var`, campos declarados e `--check`.
- ✅ Expressões: ternário `a if c else b`, `??`, `?.` e escapes de string.
- 🧪 Suíte pytest com golden cases `.lox`, testes unitários e benchmarks com baseline.
- 🌍 Suíte oficial do Crafting Interpreters (caps. 10–13) adaptada em `tests/official/`.
- 📐 Próximo passo: narrowing/generics no checker e depois o codegen LLVM.

## Rodar

Requisitos: Python 3.13 e [`uv`](https://docs.astral.sh/uv/).

```bash
uv run main.py                 # REPL (Ctrl+C/Ctrl+D para sair)
uv run main.py programa.lox    # executa um arquivo
uv run python -m lox           # mesma coisa, via pacote
uv run main.py --version       # pylox 0.1.0
uv run main.py --dump-ast prog.lox   # imprime a AST (S-expression), não executa
uv run main.py --check prog.lox      # checa os tipos, não executa
make test                      # pytest
make check                     # ruff + mypy strict + pytest
make bench                     # benchmarks vs baseline
```

Exit codes do CLI: `65` erro de compilação, `70` erro de runtime, `66` arquivo ausente,
`2` uso inválido (ex.: `--dump-ast` sem script).

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
```

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
src/             scanner, parser, AST, resolver, interpreter, classes
exemplos/        programas de exemplo (fib, fizzbuzz, closures, classes, primos)
tests/           pytest + golden cases (.lox)
tests/official/  suíte oficial do livro (caps. 10–13), adaptada
bench/           harness de performance e baseline
docs/            especificação, arquitetura e ADRs
TODO.md          roadmap e decisões em aberto
TIPOS.md         catálogo de tipos e modelo numérico
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

- **Especificação atual**: [`docs/spec/`](docs/spec/) — [léxico](docs/spec/lexico.md),
  [sintaxe](docs/spec/sintaxe.md), [semântica](docs/spec/semantica.md),
  [erros](docs/spec/erros.md).
- **Documentação técnica**: [`docs/tech/arquitetura.md`](docs/tech/arquitetura.md).
- **Decisões de design (ADRs)**: [`docs/adr/`](docs/adr/).
- **Roadmap**: [`TODO.md`](TODO.md) · **tipos**: [`TIPOS.md`](TIPOS.md) ·
  **ideias**: [`IDEIAS.md`](IDEIAS.md).

> A especificação descreve o que o código faz **hoje** (Lox do livro + `val`/`var`,
> `Int`/`Float`, ranges/`for-in`, herança `class B(A)`, defaults/campos, checker
> `--check` e `fn`/`elif`/`;` opcional). O que falta — `?.`, `??`, narrowing/generics,
> interpolação — está nos documentos de roadmap e ainda **não** está implementado.
