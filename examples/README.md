# Examples

Small programs that exercise the current language. Run them with:

```bash
uv run main.py examples/fib.lx
# or
uv run python -m loxia examples/fib.lx
```

| File | What it shows |
| --- | --- |
| `fib.lx` | functions, recursion, `if`/`return`, `for-in` |
| `fizzbuzz.lx` | `%`, `else if`, ranges |
| `closures.lx` | closures over the declaration environment |
| `classes.lx` | classes, `class B(A)`, `super.init`, `this`, a field not taken from a parameter |
| `primes.lx` | functions, `for-in`, early return |
| `quicksort.lx` | typed lists, indexing, `push`, `for-in` |
| `sales.lx` | stdlib T2 end to end: CSV → aggregation → formatted table → JSON |
| `dto_models.lx` | one model as class, tuple alias and enum: what each costs, structural `==` vs identity, exhaustive `match`, and rows arriving as `List[Any]` |

All files are run by `tests/test_examples.py` and must pass `--check`; the backend I4 test
also compiles every example. The smaller programs are part of the determinism corpus, so
keep them deterministic and free of host-dependent output.

Add a new example only when it demonstrates a real language or stdlib feature; keep
the output small and free of addresses, timestamps and absolute paths.

## Monorepo

`monorepo/` is a small project with a `path` dependency (`shared = { path = "lib" }`),
a committed `loxia.lock` and a runnable app:

```bash
uv run loxia run --frozen examples/monorepo/app/main.lx
cd examples/monorepo && uv run loxia lock --check
```

It is covered by `tests/test_monorepo.py` and by the backend differential test.
