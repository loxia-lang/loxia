# Exemplos

Programas pequenos que exercitam a linguagem atual. Rodam com:

```bash
uv run main.py exemplos/fib.lx
# ou
uv run python -m loxia exemplos/fib.lx
```

| Arquivo | O que mostra |
| --- | --- |
| `fib.lx` | funções, recursão, `if`/`return`, `for-in` |
| `fizzbuzz.lx` | `%`, `else if`, ranges |
| `closures.lx` | closure sobre ambiente de declaração |
| `classes.lx` | classes, `class B(A)`, `super.init`, `this`, campo sem parâmetro |
| `primos.lx` | funções, `for-in`, retorno antecipado |

O clássico quicksort fica para quando `List` existir (P2).
