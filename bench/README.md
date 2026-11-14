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
| `branchy` | 502,54 ms | 1,1 ms | >100x |
| `calls_closures` | 532,14 ms | 1,2 ms | >100x |
| `classes_methods` | 480,66 ms | 3,1 ms | >100x |
| `collections` | 254,74 ms | 181,9 ms | 1,4x |
| `enum_match` | 393,22 ms | 2,5 ms | >100x |
| `float_math` | 638,33 ms | 1,8 ms | >100x |
| `gc_churn` | 124,36 ms | 2,8 ms | 45,0x |
| `loop_sum` | 549,50 ms | 1,2 ms | >100x |
| `nested_loop` | 347,96 ms | 1,1 ms | >100x |
| `string_concat` | 243,84 ms | 141,6 ms | 1,7x |
| `string_scan` | 665,57 ms | 9,1 ms | 73,4x |

Leitura: o ganho é enorme em chamadas, classes, enums, float e laços; `collections` e
`string_concat` continuam presos ao custo de alocação/GC e ao algoritmo de concatenação
O(n²), não ao codegen. `string_scan` usa `join` + `charCodeAt` e mede a melhora do cache de
code points. Os números >100x são limitados pelo startup do binário (~1 ms).
