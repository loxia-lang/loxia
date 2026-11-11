# PyLox

Interpretador da linguagem **Lox** em Python, construído seguindo *Crafting Interpreters*
(Parte II — jlox), com o objetivo de evoluir para uma linguagem própria e um backend
**LLVM**.

- ✅ Parte II concluída: scanner, parser, resolver, funções/closures, classes e herança.
- 🧪 Suíte pytest com golden cases `.lox`, testes unitários e benchmarks com baseline.
- 📐 Próximo passo: decisões de sintaxe e sistema de tipos antes do codegen.

## Rodar

Requisitos: Python 3.13 e [`uv`](https://docs.astral.sh/uv/).

```bash
uv run main.py                 # REPL (Ctrl+C/Ctrl+D para sair)
uv run main.py programa.lox    # executa um arquivo
make test                      # pytest
make check                     # ruff + mypy strict + pytest
make bench                     # benchmarks vs baseline
```

Exit codes do CLI: `65` erro de compilação, `70` erro de runtime, `66` arquivo ausente.

## Exemplo

```lox
class Conta {
  init(saldo) {
    this.saldo = saldo;
  }

  deposita(valor) {
    this.saldo = this.saldo + valor;
  }
}

var c = Conta(10);
c.deposita(5);
print c.saldo;  // 15
```

## Estrutura

```
main.py          CLI e REPL
src/             scanner, parser, AST, resolver, interpreter, classes
tests/           pytest + golden cases (.lox)
bench/           harness de performance e baseline
docs/            especificação, arquitetura e ADRs
TODO.md          roadmap e decisões em aberto
TIPOS.md         catálogo de tipos e modelo numérico
IDEIAS.md        discussões de design (parking lot)
```

`AGENTS.md` é local (não versionado), com regras de contribuição para agentes/devs.

## Documentação

- **Especificação atual**: [`docs/spec/`](docs/spec/) — [léxico](docs/spec/lexico.md),
  [sintaxe](docs/spec/sintaxe.md), [semântica](docs/spec/semantica.md),
  [erros](docs/spec/erros.md).
- **Documentação técnica**: [`docs/tech/arquitetura.md`](docs/tech/arquitetura.md).
- **Decisões de design (ADRs)**: [`docs/adr/`](docs/adr/).
- **Roadmap**: [`TODO.md`](TODO.md) · **tipos**: [`TIPOS.md`](TIPOS.md) ·
  **ideias**: [`IDEIAS.md`](IDEIAS.md).

> A especificação descreve o que o código faz **hoje** (Lox do livro + `val`/`var`).
> A sintaxe planejada (`;` opcional, `fn`, pipes, tipos) está nos documentos de roadmap e
> ainda **não** está implementada.
