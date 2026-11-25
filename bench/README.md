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

## Orçamento de monomorfização (2026-11-17)

`make monomorph` (local, não é gate) mede o que o corpus pede e o custo do teto do
[ADR-0063](../docs/adr/0063-orcamento-monomorfizacao.md):

- replay do corpus (`tests/cases`, 163 casos medidos; 105 pulados por import/erro de
  `--check`): máximo de **15** funções especializadas, **4** layouts de classe,
  profundidade **1** e nome mangled **25 bytes**;
- sintético (`N` classes + `N` chamadas `id(Ci())`): 16 → 80 KiB, 64 → 299 KiB,
  128 → 593 KiB, 256 → **1.183 KiB em ~327 ms**; 257 é recusado com `E4003`.

Conclusão: os limites iniciais (256 funções, 256 classes, profundidade 8, 1024 bytes)
ficam ~17x acima do maior caso do corpus e o teto custa ~1,2 MiB/~0,33 s nesta máquina.

## `SourceIndex` (2026-11-24)

`uv run python bench/source_index.py` mede a construção do índice do front-end (issue #130)
sem subprocesso e sem CI. O parse fica fora do tempo: o alvo é indexar nós + nomes de
declaração + nomes de tipo e responder `at()` no caminho de navegação local.

```bash
uv run python bench/source_index.py                 # compara com o baseline
uv run python bench/source_index.py --repeat 5      # mais amostras
uv run python bench/source_index.py --update        # regrava o baseline
uv run python bench/source_index.py --json          # inclui o por-arquivo
```

Corpus de 2026-11-24 (369 arquivos, 338 parseáveis): 36 827 spans (2 928 de tipo,
3 295 de nome), total ~625 ms, mediana 0,589 ms/arquivo, p95 7,939 ms/arquivo e
`at()` ~13,9 µs/consulta. A regra é **≤ 2×** o total/mediana do
[`source_index_baseline.json`](source_index_baseline.json); o guard determinístico é
[`tests/test_source_index_budget.py`](../tests/test_source_index_budget.py) e não mede tempo.

## LSP end-to-end (2026-11-24)

`uv run python bench/lsp.py` (ou `make bench-lsp`) sobe o servidor real (`main.py lsp`) e
mede o caminho JSON-RPC sobre stdio: startup/initialize, didOpen com imports, hover,
definition, references cross-file (frio e quente), documentHighlight, rename local, completion,
documentSymbol e didChange. Não roda no CI.

```bash
uv run python bench/lsp.py                  # compara com o baseline
uv run python bench/lsp.py --repeat 7       # mais sessões (cada uma sobe um servidor)
uv run python bench/lsp.py --update         # regrava o baseline
uv run python bench/lsp.py --json
```

Workspace gerado em diretório temporário (`lib.lx` com classe/funções e `main.lx` com
`import`, anotação, `std.lists` e variável local), então os offsets são estáveis e não
aparecem paths absolutos. Mediana de 2026-11-24 nesta máquina: startup ~97 ms, didOpen
~38 ms, references cross-file ~66 ms na primeira consulta e ~1,2 ms com o cache do
workspace, didChange ~35 ms, completion ~1,4 ms; hover,
definition, highlight, rename e documentSymbol abaixo de 1 ms. A tolerância é **1,5×** o
baseline ([`lsp_baseline.json`](lsp_baseline.json)); startup e recheck dominam, então
variações de máquina aparecem primeiro neles.
