# ADR-0022 — Lambdas com `fn(x) => ...` e tipagem contextual

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0020](0020-assinaturas-explicitas.md), [ADR-0021](0021-tipos-de-funcao.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [`../../TODO.md`](../../TODO.md) §1,
  [`../spec/semantica.md`](../spec/semantica.md),
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/frontend/scanner.py`](../../src/frontend/scanner.py),
  [`src/frontend/token_type.py`](../../src/frontend/token_type.py), [`src/frontend/expr.py`](../../src/frontend/expr.py),
  [`src/frontend/parser.py`](../../src/frontend/parser.py), [`src/semantics/resolver.py`](../../src/semantics/resolver.py),
  [`src/execution/interpreter.py`](../../src/execution/interpreter.py),
  [`src/execution/lox_function.py`](../../src/execution/lox_function.py), [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`src/frontend/ast_printer.py`](../../src/frontend/ast_printer.py),
  [`tests/test_parser.py`](../../tests/test_parser.py),
  [`tests/test_checker.py`](../../tests/test_checker.py),
  [`tests/test_interpreter.py`](../../tests/test_interpreter.py)

## Contexto

Depois do ADR-0021, funções já podiam ser passadas como argumento, mas só se fossem
**nomeadas**:

```lox
fn dobro(n: Int) -> Int { return n * 2 }
aplicar(dobro, 3);
```

Para callbacks curtos isso é cerimônia. Python resolve com `lambda x: x * 2`, mas essa
forma não encaixa aqui: `:` já é anotação de tipo (`x: Int`) e separador de mapa
(`{"a": 1}`), e lambda em Python não aceita bloco nem anotação. A decisão foi usar o
`fn` que já existe, com `=>` para o corpo de expressão.

## Decisão

### Sintaxe

```
lambda := "fn" "(" params? ")" ("->" type)? ( "=>" expression | block )
```

```lox
val dobro = fn(x: Int) => x * 2

val soma = fn(a: Int, b: Int) {
  return a + b
}

fn aplicar(f: fn(Int) -> Int, x: Int) -> Int { return f(x) }
print aplicar(fn(x) => x * 2, 3);
```

- `=>` introduz um corpo de **expressão**; o valor da expressão é o retorno.
- `{ ... }` introduz um corpo de **bloco** com `return` explícito, igual a funções.
- `-> Tipo` é opcional antes de qualquer corpo; sem ele, o retorno é inferido.
- `fn(` em posição de expressão é lambda; `fn nome(` é declaração de função.
- Parâmetros seguem as regras de funções (nome, `: Tipo`, `var x`), **exceto defaults**:
  `fn(x: Int = 1) => ...` é erro. Defaults em lambda foram adiados para não complicar a
  aridade contextual.
- Sem retorno implícito do último valor do bloco: duas semânticas de bloco seria pior.
- Sem parâmetro único sem parênteses (`fn x =>`), sem trailing closure (`xs.map { ... }`)
  e sem generics nesta etapa.

### Tipagem contextual

O checker usa o **tipo esperado** para preencher parâmetros sem anotação:

```lox
fn aplicar(f: fn(Int) -> Int, x: Int) -> Int { return f(x) }

aplicar(fn(x) => x * 2, 3);       # x: Int
aplicar(fn(x) { return x * 2 }, 4);  # x: Int, retorno Int
```

Sem contexto, o parâmetro precisa de anotação:

```lox
val f = fn(x: Int) => x * 2;   # ok
val g = fn(x) => x * 2;        # Parameter 'x' needs a type annotation
```

O contexto vale para argumento de chamada, variável/campo anotado, `return` e elemento de
`List`/`Map`. `Any` não fornece contexto; para código dinâmico, anote `x: Any`.

### Retorno

- Corpo de expressão: infere o tipo da expressão.
- Corpo de bloco: se `-> T` existir, checa os `return`s contra `T`; se não, infere.
- Bloco sem `return` e sem `-> T` infere `Nil`; se o contexto espera um retorno não-nil,
  erro.
- Se o bloco pode terminar sem `return` e o retorno declarado não aceita `Nil`, erro
  (`Lambda body must return Int.`).
- Misturar `return 1` e `return "x"` em **returns separados** exige anotação
  (`Lambda returns Int | String; annotate the return type.`). `Int | Nil` é permitido.
- `return` sem valor dentro de lambda conta como `Nil`.

### Escopo e runtime

- A lambda é uma closure sobre o ambiente onde foi avaliada; `LoxFunction` já faz isso.
- `this`/`super` são **lexicais**: uma lambda dentro de método enxerga o `this` do método.
- `return` dentro da lambda retorna da lambda, não da função externa.
- `print` de lambda sai `<lambda>` (determinístico).
- Recursão direta no inicializador (`val f = fn... f...`) não funciona; use
  `var f; f = fn...` ou uma `fn` nomeada.

## Consequências

### Positivas

- Callbacks inline, sem declarar funções de apoio:

  ```lox
  print aplicar(fn(x) => x * 2, 3);
  ```

- O corpo da lambda é checado contra o tipo esperado, inclusive chamadas dentro dele.
- Nenhuma sintaxe nova para o runtime além do token `=>`; funções já eram valores.
- `this`/`super` continuam léxicos, que é o comportamento esperado dentro de métodos.
- Mensagens de erro dizem qual parâmetro falta anotar, qual retorno falta e quando a
  assinatura não bate.

### Negativas / custos

- Sem `fn x =>` nem trailing closure; callbacks muito curtos ainda pagam `fn(...)`.
- Bloco exige `return`; quem vem de linguagens com retorno implícito pode estranhar.
- Mistura de retornos não-nil exige anotação; sem `is T`, união não-nil é difícil de
  estreitar.
- Defaults em parâmetro de lambda ficaram de fora; use função nomeada se precisar.
- Inferência de retorno de bloco é conservadora: se o bloco pode cair no fim, entra `Nil`.
- O checker pode reportar mais de um erro para uma lambda com assinatura errada (corpo e
  argumento); é ruído de diagnóstico, não ambiguidade semântica.
- Ainda não há generics, então `map`/`filter` genéricos continuam em T3b.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `lambda x: x * 2` (Python) | `:` já é anotação de tipo e separador de mapa; lambda tipada viraria `lambda x: Int: ...`, e não cabe bloco/`return` |
| `(x) => x * 2` | Mais curto, mas começa como agrupamento; exige lookahead e `(x) { ... }` fica estranho |
| `|x| x * 2` (Rust) | `\|` é bitwise e aparece em uniões `A \| B`; parser ambíguo demais |
| `fn(x) -> x * 2` | `->` já é tipo de retorno; impediria anotar o retorno da lambda |
| `{ x => ... }` / trailing closure | `{` no início de expressão é literal de mapa; fica para depois |
| Retorno implícito do último valor do bloco | Criaria uma segunda semântica de bloco só para lambda |
| Defaults em parâmetros de lambda | Complica a aridade contextual e não é necessário agora |
| Inferir união não-nil automaticamente | Sem `is T`, o chamador quase não consegue usar o valor |

## Como verificar

- `tests/test_scanner.py` (`=>`);
- `tests/test_parser.py` (corpo de expressão, bloco, retorno, statement, defaults);
- `tests/test_ast_printer.py` (nó `lambda`);
- `tests/test_interpreter.py` (closure, `return`, `this`, `stringify` `<lambda>`);
- `tests/test_checker.py`:
  - `test_lambda_parameters_are_typed_from_context`;
  - `test_lambda_without_context_needs_annotations`;
  - `test_lambda_mixed_returns_need_an_annotation`;
  - `test_lambda_annotated_mixed_returns_are_clean`;
  - `test_lambda_missing_return_is_an_error`;
  - `test_lambda_captures_this_type`;
  - `test_lambda_wrong_signature_is_rejected`;
- `make check` verde.

Critério para revisar: quando generics (T3b), trailing closure, parâmetro único sem
parênteses ou retorno implícito de bloco entrarem; ou se a tipagem contextual se mostrar
insuficiente na prática.
