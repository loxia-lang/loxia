# Exemplos

Programas pequenos que exercitam a linguagem atual. Rodam com:

```bash
uv run main.py exemplos/fib.lox
# ou
uv run python -m lox exemplos/fib.lox
```

| Arquivo | O que mostra |
| --- | --- |
| `fib.lox` | funções, recursão, `if`/`return`, `for-in` |
| `fizzbuzz.lox` | `%`, `else if`, ranges |
| `closures.lox` | closure sobre ambiente de declaração |
| `classes.lox` | classes, `class B(A)`, `super.init`, `this`, campo sem parâmetro |
| `primos.lox` | funções, `for-in`, retorno antecipado |

O clássico quicksort fica para quando `List` existir (P2).
