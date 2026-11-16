# ADR-0029 — Conversões (`as`, parse) e `math.*` determinístico

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0006](0006-int-float-separados.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [ADR-0016](0016-api-stdlib-hibrida.md),
  [ADR-0026](0026-freeze-1.0.md), [ADR-0028](0028-overflow-debug.md),
  [`../spec/semantica.md`](../spec/semantica.md), [`../spec/sintaxe.md`](../spec/sintaxe.md),
  [`../spec/semantica.md`](../spec/semantica.md), [`../spec/erros.md`](../spec/erros.md)
- **Implementação:** [`loxia_core/frontend/expr.py`](../../loxia_core/frontend/expr.py), [`loxia_core/frontend/parser.py`](../../loxia_core/frontend/parser.py),
  [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py), [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py),
  [`loxia_core/execution/numeric.py`](../../loxia_core/execution/numeric.py), [`loxia_core/execution/native_module.py`](../../loxia_core/execution/native_module.py),
  [`loxia_core/execution/natives/parse.py`](../../loxia_core/execution/natives/parse.py),
  [`loxia_core/execution/natives/math.py`](../../loxia_core/execution/natives/math.py),
  [`loxia_core/execution/natives/modules.py`](../../loxia_core/execution/natives/modules.py)

## Contexto

O `D-8` estava em aberto desde o ADR-0016. Faltava decidir:

- sintaxe de cast (`as`, função ou construtor);
- como falhar (erro fatal, `nil` ou `Result`);
- API de parse;
- funções matemáticas e o impacto no determinismo (I3).

A 1.0 não tem `Result` nem módulos; a stdlib é híbrida e o prelúdio é mínimo. Além disso,
`log`, `exp`, `sin`, `cos`, `tan` e `pow` vêm da libm e não são bit-a-bit portáveis, o que
colide com I3.

## Decisão

### 1. Cast explícito com `as`

```lox
val i = 3.9 as Int
val f = 3 as Float
val d = anyValue as Dog
```

- `as` é keyword e operador de precedência alta: liga mais forte que `*` e mais fraca que
  unary (`-x as Int` = `(-x) as Int`, `x as Int + 1` = `(x as Int) + 1`).
- Não existe cast implícito. `as` é uma asserção/conversão explícita.
- `Int as Float`: sempre permitido; arredonda para f64 e pode perder precisão acima de
  `2^53`.
- `Float as Int`: trunca em direção a zero; `NaN`, `Inf` ou fora de `[INT_MIN, INT_MAX]`
  é erro fatal de runtime.
- `Any as T`: checagem de runtime. Para `Int`/`Float`, converte valores numéricos; para
  classes/listas/mapas, usa a mesma checagem de `is`.
- `T as T` é identidade; `x as Any` devolve o valor.
- Target union (`as Int?`, `as Int | String`) ainda não é suportado; use narrowing/`is`.
- String não vira número por cast; use `parse`.

### 2. Parse devolve `T?`

```lox
val n = Int.parse("42")      # Int?
val f = Float.parse("3.14")  # Float?
```

- `Int.parse`/`Float.parse` são membros de namespaces nativos `Int`/`Float`.
- Texto inválido, vazio, com espaços ou fora do range devolve `nil`; não há crash.
- `Int.parse` aceita sinal opcional e dígitos decimais; `Float.parse` aceita decimal com
  ponto e expoente opcional. `NaN`/`Inf` não são produzidos.
- Não existe `42.toString()`: `str(42)` é a conversão para texto.

### 3. Núcleo de `math.*` determinístico

```lox
math.abs(x)  math.min(a, b)  math.max(a, b)  math.clamp(x, lo, hi)
math.floor(x)  math.ceil(x)  math.round(x)  math.trunc(x)
math.sqrt(x)
```

- `math` é um namespace nativo somente leitura; não é classe instanciável.
- `abs/min/max/clamp` aceitam `Int`/`Float` e promovem quando misturam; `floor/ceil/round/
  trunc` devolvem `Int` e exigem valor finito no range i64; `sqrt` devolve `Float`
  (`sqrt(negativo)` → `NaN`).
- `round` arredonda metade para longe de zero.
- `min/max` com `NaN` devolvem `NaN`; `clamp` exige `low <= high`.
- `abs(INT_MIN)` obedece ao ADR-0028: erro no `--debug`, wrap no release.
- **Fora da 1.0**: `log`, `exp`, `sin`, `cos`, `tan`, `pow` e constantes como `math.pi`.
  Esses vêm da libm e ficam fora do corpus I3 até existir uma biblioteca determinística ou
  uma decisão explícita de exceção.

## Consequências

- `as` é a única forma de converter `Float` em `Int`; permanece explícito e falível.
- Parse é a via segura para entrada de texto, com `nil` em vez de erro.
- O prelúdio ganha três namespaces (`Int`, `Float`, `math`), mas não ganha 15 funções
  globais.
- I3 vale para todo `math.*` implementado; transcendentais ficam de fora.
- O backend precisará de `fptosi` com guarda para `Float as Int` e de `f64` para `math`.
- O cast de `Any` para classe depende do runtime; o backend L0–L2 rejeita `Any`, então
  esse caminho fica no tree-walk/interpretado até a representação dinâmica existir.

## Alternativas rejeitadas

- **`to_int`/`to_float`**: verboso e não cobre downcast de `Any`.
- **`Int(x)`/`Float(x)`**: confunde tipo com função/construtor.
- **`as` retornando `T?`**: contamina o tipo de toda conversão e esconde o erro; parse já
  cobre o caso esperado.
- **Funções `math` globais**: poluiria o prelúdio e dificultaria módulos futuros.
- **Implementar transcendentais agora**: quebraria I3 por diferenças de libm.
