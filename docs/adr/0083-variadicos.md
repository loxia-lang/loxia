# ADR-0083 — Variádicos `...args` e spread final

- **Status:** accepted (implementado: parser, checker, tree-walk, backend e stdlib)
- **Data:** 2026-11-15
- **Relaciona:** [ADR-0009](0009-defaults-e-campos.md) (defaults),
  [ADR-0027](0027-generics-t3b.md) (generics), [ADR-0066](0066-orcamento-e-gate-sintatico.md)
  (orçamento), [ADR-0072](0072-stdlib-batteries.md) (fmt)

## Contexto

As APIs de composição da stdlib precisam aceitar um número variável de argumentos. O
caso concreto é `fmt.format(template, ...args)`: hoje ele recebe `List[Any]`, o que obriga
o chamador a montar uma lista mesmo para dois valores. Sem variádicos, `print` também não
pode virar função sem uma lista explícita. A sintaxe `...` já era a candidata registrada
em `IDEIAS.md`; ela não colide com `..` (range) nem com `*` (multiplicação).

## Decisão

### 1. Declaração

O último parâmetro pode ser variádico, prefixado por `...`:

```lox
fn soma(...xs: Int) -> Int
fn rotulo(prefixo: String, ...xs: String) -> String
class Junta { fn juntar(sep: String, ...xs: String) -> String }
val f = fn(prefixo: String, ...xs: Int) => prefixo
```

- A anotação é o **tipo do elemento**: dentro do corpo `xs` é `List[Int]`, `List[String]`
  etc. Sem anotação é erro no `--check` (inclusive em lambda).
- O variádico é sempre o **último** parâmetro, não tem default e só pode haver um.
- Vale para funções, métodos, métodos de interface e lambdas. `init` fica **fora** da v1:
  aridade de construtor, herança e `super.init` teriam regras próprias; o checker recusa
  com `Variadic parameters aren't supported in 'init' yet.`.
- Defaults nos parâmetros fixos anteriores continuam valendo (`fn f(a: Int = 1, ...xs: Int)`).

### 2. Chamada e spread

- Chamada comum: os argumentos extras viram a lista do rest. `soma(1, 2, 3)` e `soma()`
  são válidos; a aridade mínima é a dos parâmetros fixos sem default.
- Spread final: `f(1, ...xs)` expande `xs` **somente no parâmetro variádico**. O spread
  precisa ser o último argumento e todos os parâmetros fixos devem ser passados
  explicitamente antes dele. `f(...xs)` só é válido quando `f` não tem parâmetros fixos.
- Não há spread em listas/mapas/literais nem no meio de argumentos
  (`f(...xs, 2)` é erro de parser; `f(...xs)` num `f(a: Int, ...xs: Int)` é erro de
  checker). Isso evita concatenação dinâmica e mantém a aridade verificável.
- O spread exige `List[T]` cujo elemento case com o tipo do rest; listas vazias são
  válidas.

### 3. Checker

`FnTy` ganhou `variadic: bool`; o último item de `params` é o **tipo do elemento** e
`min_params` conta só os fixos sem default. `fixed_params` é `len(params)-1` quando
variádico.

- Chamada comum: `count >= min_params`; cada argumento além dos fixos é checado contra o
  elemento do rest.
- Spread: `count == fixed_params + 1`; os fixos são checados normalmente e o último
  argumento contra `List[elemento]`.
- Atribuição de função variádica a `fn(...T) -> R` usa a mesma regra; variádico e não
  variádico não são atribuíveis entre si.
- Lambdas contextuais inferem o elemento do rest a partir de `fn(...T) -> R`; lambdas
  generalizadas (`val f = fn(...)`) exigem anotação no rest.

### 4. Runtime (tree-walk)

- `LoxFunction.min_arity` ignora o variádico; `max_arity` é ilimitado.
- `call` liga os parâmetros fixos e cria um `LoxList` novo com os argumentos restantes
  (a lista é mutável, como qualquer `List`).
- Chamada com spread: o interpretador avalia a lista e **expande** seus elementos antes
  da checagem de aridade; com a regra “spread só preenche o rest”, o resultado é
  equivalente a passar os elementos um a um.

### 5. Backend

- O ABI do rest é um **`List`** (ponteiro), não um array de tamanho variável. O último
  parâmetro de `FnSig.params` é a lista; `FnSig.vararg_element` guarda o descritor do
  elemento.
- Chamada comum: empacota os extras numa `List` (boxeando cada elemento) e passa a lista;
  defaults dos fixos são preenchidos como antes.
- Spread: passa a lista diretamente como rest; os fixos são coagidos normalmente.
- Funções variádicas como valor, métodos, defaults de métodos de interface e lambdas
  usam o mesmo caminho. `init` variádico não existe no checker, então não chega aqui.

### 6. Stdlib

`std.fmt.format` passa a ser `fn format(template: String, ...values: Any) -> String`;
`values` continua `List[Any]` no corpo. A chamada vira
`fmt.format("{} + {} = {}", a, b, c)` e o spread `fmt.format(template, ...args)` funciona
quando `args` é `List[Any]`. O caso `std_fmt.lx` foi migrado; não há mudança de
comportamento de formatação.

## Consequências

- `fmt.format` e futuras APIs (`print`, `join`, `log`) deixam de exigir lista manual.
- O ABI não muda para funções não variádicas; o custo é uma lista alocada por chamada
  variádica.
- A regra “spread só preenche o rest” é mais restrita que Python/Kotlin, mas mantém
  aridade e tipos verificáveis sem concatenar listas no meio da chamada.
- `nil` continua sendo um elemento válido de `List[Any]`; só `next()` de iterador usa
  `nil` como sentinela.
- `init` variádico, spread no meio e spread em literais ficam para depois, se houver dor.

## Portão sintático (ADR-0066)

1. **Substituição:** não cria segunda forma de declaração; `...` é um prefixo local no
   parâmetro/argumento. A alternativa seria uma lista explícita, que é o que a feature
   remove.
2. **Decidibilidade local:** no parâmetro, `...` antes do identificador; na chamada,
   depois de `(`/`,`; o parser sabe se é spread sem lookahead.
3. **Precedência:** não cria nível; `...` não é operador de expressão.
4. **Forma canônica:** `...xs: T` e `f(a, ...xs)`; spread no meio e no início (fora de
   `f(...xs)` sem fixos) são recusados. Nenhuma palavra-chave nova; o token `...` entra
   como operador/pontuação na grammar.

## Alternativas

| Alternativa | Por que não |
| --- | --- |
| `*args` | `*` já é multiplicação e spread de lista; `...` é a grafia registrada e não ambígua |
| `vararg args: T` | palavra-chave nova sem necessidade; `...` é mais curto e local |
| `...xs: List[T]` | obrigaria `List[...]` em toda assinatura e não deixa claro o elemento |
| Spread em qualquer posição | exigiria concatenar listas e checar aridade dinâmica; mais backend e mais erros |
| `init` variádico | aridade de classe/herança e `super.init` têm regras próprias; fica fora |
| Só parâmetros, sem spread | não permite `fmt.format(template, ...args)` nem repassar listas |

## Como Verificar

- `tests/cases/variadic.lx` no `l6`: funções, método, default antes do rest, zero
  variádicos, spread final, genérico, lambda anotada, função variádica como valor.
- `tests/cases/std_fmt.lx`: `format` variádico e spread.
- `tests/test_checker.py::test_variadic_errors`: default, `init`, spread em não-variádico,
  spread com fixos faltando, elemento errado e argumento errado.
- `tests/test_parser.py`: parâmetro/spread, `fn(...T)` e variádico fora do fim.
- `tests/test_scanner.py`: `...` antes de `..`/`.`; `make grammar` para o token.
- `make check` e `make bench`.
