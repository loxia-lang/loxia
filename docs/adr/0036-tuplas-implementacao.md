# ADR-0036 — Tuplas: implementação da v1

- **Status:** accepted

> **Atualização:** `for-in`, `is (A, B)` e `as (A, B)` foram implementados depois deste
> ADR (eram adiados); o que resta é destructuring aninhado e backend (L6).
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0030](0030-tuplas.md), [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0015](0015-listas-tipadas.md), [ADR-0017](0017-mapas-hash.md),
  [ADR-0031](0031-backend-nativo.md), [`../../TIPOS.md`](../../TIPOS.md) §2.3,
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/frontend/expr.py`](../../src/frontend/expr.py),
  [`src/frontend/stmt.py`](../../src/frontend/stmt.py),
  [`src/frontend/parser.py`](../../src/frontend/parser.py),
  [`src/frontend/ty.py`](../../src/frontend/ty.py),
  [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`src/semantics/resolver.py`](../../src/semantics/resolver.py),
  [`src/execution/lox_tuple.py`](../../src/execution/lox_tuple.py),
  [`src/execution/interpreter.py`](../../src/execution/interpreter.py),
  [`tests/test_parser.py`](../../tests/test_parser.py),
  [`tests/test_checker.py`](../../tests/test_checker.py),
  [`tests/test_interpreter.py`](../../tests/test_interpreter.py),
  [`tests/cases/tuples.lox`](../../tests/cases/tuples.lx)

## Contexto

O ADR-0030 decidiu a sintaxe e a semântica básica de tuplas, mas deixou a implementação
pós-1.0/backend e três pontos em aberto: variância, profundidade do destructuring e
`for-in`/`is (A, B)`. A implementação chegou antes do backend (que segue pausado no L4),
como trabalho de linguagem/checker.

## Decisões

1. **Covariante por elemento.** `(Dog, Int)` é atribuível a `(Animal, Int)` e
   `(Int, String)` a `(Any, Any)`. É *sound* porque tuplas são imutáveis (não há escrita
   para quebrar a covariança), e é a mesma lógica do retorno de função covariante.
   `_assignable` compara elemento a elemento; aridade diferente não é atribuível.
2. **Destructuring flat, `val` e `var`, com anotação opcional.**
   `val (a, b) = t`, `var (c, d) = t` e `val (a, b): (Int, String) = t`. Nomes são
   bindings novos (imutáveis em `val`, mutáveis em `var`); aridade errada, nome duplicado
   e inicializador que não é tupla são erros. `Any` só pode ser desestruturado com
   anotação (que dá o tipo das partes). Aninhamento `val (a, (b, c)) = t` fica para depois.
3. **`for x in t` e `is (A, B)` continuam adiados**, com erro explícito:
   `Can't iterate over a tuple yet; index with t[i].` e
   `is doesn't support tuple types yet.` (`as` idem). Iterar tupla heterogênea exige
   decidir o tipo do elemento; `is` exige teste por posição. Ambos são features, não
   bloqueios da v1.
4. **Tuplas não são hasháveis** e não podem ser chave de `Map`. Hash estrutural exigiria
   canonicalizar números dentro da tupla (`1` vs `1.0`), o mesmo motivo pelo qual `Float`
   já está fora das chaves (ADR-0017). Chaves continuam `String`/`Int`/`Bool`.
5. **Índice literal fora do range é erro de compilação.** `t[2]` num tipo
   `(Int, String)` acusa `Tuple index 2 out of bounds for length 2.` no `--check`.
   Índice dinâmico (`t[i]`) tem tipo `Int | String` (união dos elementos) e bounds em
   runtime (`Tuple index 5 out of bounds for length 2.`), como `List`.
6. **Representação de runtime `LoxTuple(items)`**, não o `tuple` do Python direto: evita
   confundir com valores internos e deixa `stringify`/igualdade explícitos. Igualdade
   estrutural elemento a elemento (com a igualdade da linguagem, então `1 == 1.0` vale
   dentro); formatação `(1, "a")` com strings citadas, recursiva, e `(...)` se houver
   ciclo via lista/mapa.

## Consequências

- `(a, b)`, `(A, B)`, `t[0]`, `len(t)`, `val/var (a,b) = t` e `==` funcionam no
  interpretador e no `--check`.
- O backend rejeita tuplas com exit 65 e `not supported by the backend yet` (L6), sem
  lowering silencioso.
- `t[0] = x` continua erro (`Only lists and maps can be indexed.`); tuplas são imutáveis.
- `for-in`/`is`/destructuring aninhado ficam no TODO; a documentação os lista como
  pendentes, não como suportados.
- Como tuplas não são chave de `Map`, a consistência de hash do ADR-0017 não é afetada.

## Alternativas rejeitadas

- **Invariante (como `List`/`Map`):** mais simples, mas perde subtipagem sem ganho de
  segurança, já que não há mutação.
- **Hashável:** inconsistente com `1 == 1.0` sem canonicalização de números na chave.
- **Índice dinâmico proibido:** o ADR-0030 já decidiu união + bounds em runtime.
- **Erro de runtime para índice literal:** seria uniforme com `List`, mas o tamanho da
  tupla é estático; falhar no `--check` é mais cedo e mais claro.
- **Usar `tuple` do Python:** vaza `repr` do Python (`(1, 'a')`) e confunde igualdade.
