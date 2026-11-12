# Changelog

Todas as mudanças relevantes da linguagem/interpretador. O escopo de cada versão está em
[`ESCOPO.md`](ESCOPO.md); decisões fechadas em [`docs/decisoes.md`](docs/decisoes.md).

## [1.0.0] — 2026-11-12

**1.0.0 é a versão de referência da linguagem no tree-walk.** Não há backend nativo
publicado; o LLVM L0–L2 é pós-1.0. A release é local (sem publicação externa).

### Adicionado

- Interpretador tree-walk completo dos caps. 4–13: scanner, parser, resolver, funções,
  closures, classes, `this`, `super` e herança.
- `val`/`var` com imutabilidade de binding, parâmetros imutáveis e `var` explícito.
- `fn`, `elif`, `;` opcional, ternário, `??`, `?.`, interpolação e escapes.
- `Int`/`Float` separados, promoção só `Int → Float`, `//`, `%`, `**` e bits i64.
- Ranges, `for-in`, `List[T]` e `Map[K, V]`.
- Defaults, campos declarados, lambdas e tipos de função.
- Checker gradual `--check`: anotações, inferência local, `T?`, uniões, `is T` e narrowing.
- Generics T3b: funções `fn id[T]`, inferência na chamada, sem constraints.
- Conversões D-8: `as` explícito, `Int.parse`/`Float.parse` → `T?` e `math.*`
  determinístico.
- `--debug` com checagem de overflow de `Int`; release continua wrapping.

### Mudado

- Freeze da 1.0: erro de runtime fatal (exit 70), sem `try`/`Result`.
- `clock` removido do prelúdio; prelúdio determinístico (`len`, `str`, `repr`, `range`,
  `Int`, `Float`, `math`).
- Strings UTF-8 com `len` em code points; identificadores ASCII.
- `print` continua statement; single-file.
- `Any` permanece na linguagem, mas o backend L0–L2 o rejeita.

### Fora da 1.0

Backend LLVM, tuplas, classes/métodos genéricos, constraints/traits, módulos/stdlib,
contratos/JSON, `Result`/`try`, variádicos, trailing closure, `match`/enums, diagnósticos
com spans/caret e transcendentais de `math`. Ver [`ESCOPO.md`](ESCOPO.md).

### Verificação

- `make check` verde: **678 passed + 8 xfailed**, ruff e mypy strict limpos.
- Suíte oficial adaptada: 112 pass + 8 `xfail` intencionais.
- Benchmarks dentro do limite de regressão do baseline.
- `uv run main.py --version` → `pylox 1.0.0`.
