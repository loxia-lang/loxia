# Benchmarks

Harness de performance do CLI e do backend nativo. Benchmarks **não** rodam no CI:
o ruído de runner domina. Rode localmente quando tocar caminho quente.

```bash
make bench          # interpretador vs bench/baseline.json
make bench-native   # compila com --emit=exe e mede o binário
make baseline       # regrava o baseline do interpretador (intencional)
```

## Metodologia

- Cada caso roda em processo separado; a mediana de `--repeat` amostras é comparada
  com o baseline.
- O interpretador inclui o boot do Python; o nativo inclui o startup do binário. Para
  casos que ficam abaixo de ~50 ms no nativo, o tempo é dominado por startup e o
  speedup medido é um **limite inferior**, não o custo puro do workloop.
- `--native` não regrava o baseline: ele usa a mediana do interpretador como referência
  e mostra `speedup = interpretador / nativo`.
- O baseline é intencionalmente regravado ao adicionar casos novos; não regrave para
  esconder regressão de um caso existente.

## Resultado de 2026-11-14

Máquina local, `--repeat 3`, `libgc` Boehm, binário com passes `-O2`:

| caso | interpretador | nativo | speedup medido |
| --- | ---: | ---: | ---: |
| `branchy` | 504,06 ms | 1,2 ms | >100x |
| `calls_closures` | 517,18 ms | 1,3 ms | >100x |
| `classes_methods` | 473,06 ms | 3,2 ms | >100x |
| `collections` | 248,18 ms | 180,3 ms | 1,4x |
| `enum_match` | 385,62 ms | 2,5 ms | >100x |
| `float_math` | 612,97 ms | 1,7 ms | >100x |
| `gc_churn` | 115,04 ms | 2,8 ms | 41,7x |
| `loop_sum` | 537,46 ms | 1,2 ms | >100x |
| `nested_loop` | 339,13 ms | 1,1 ms | >100x |
| `string_concat` | 235,75 ms | 152,3 ms | 1,5x |

Leitura: o ganho é enorme em chamadas, classes, enums, float e laços; `collections` e
`string_concat` continuam presos ao custo de alocação/GC e ao algoritmo de concatenação
O(n²), não ao codegen. Os números >100x são limitados pelo startup do binário (~1 ms).
