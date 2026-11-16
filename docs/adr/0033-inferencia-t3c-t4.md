# ADR-0033 — Inferência de parâmetro (T3c) e generalização de lambda (T4)

- **Status:** accepted (T4); a parte **T3c** foi revertida pelo [ADR-0034](0034-t3c-revertido.md)
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0020](0020-assinaturas-explicitas.md),
  [ADR-0022](0022-lambdas.md), [ADR-0027](0027-generics-t3b.md),
  [`../../TODO.md`](../../TODO.md) §2, [`../../TIPOS.md`](../../TIPOS.md) §2.1/§2.2,
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

O T3b fez generics **explícitos** (`fn id[T]` com `x: T` e retorno `T`): o corpo é checado uma vez com
`TyVar` e cada chamada instancia por unificação. Fora disso, anotar era obrigatório em todo
parâmetro (ADR-0020) e lambda sem tipo esperado exigia anotação (ADR-0022):

```lox
fn igual(x, y) -> Bool { return x == y }   # erro: 'x' precisa de anotação
val id = fn(x) => x                         # erro: sem contexto
```

T3c pedia inferência de parâmetro; T4, generalização (let-polymorphism) para funções
genéricas implícitas.

## Decisão

> **Revisão:** esta seção (T3c) foi **revertida** pelo [ADR-0034](0034-t3c-revertido.md);
> o ADR vale pelo T4.

### T3c — parâmetro sem anotação é um parâmetro de tipo implícito (revertido)

Em **função de topo**, cada parâmetro sem anotação vira uma `TyVar` fresca; a assinatura
passa a ser implicitamente genérica e a chamada usa a mesma unificação do T3b. Os nomes são
sintéticos e determinísticos (`T`, `T2`, ...), nunca visíveis para o usuário.

```lox
fn igual(x, y) -> Bool { return x == y }   # ≡ fn igual[T, U] com x: T e y: U
print igual(1, 1)                           # T = Int, U = Int
print igual("a", "b")                       # T = String, U = String
print igual(1, "a")                         # legal: x e y são independentes
```

- Dois parâmetros sem anotação são **independentes**, não o mesmo `T`.
- **Métodos não entram:** generic methods não são suportados (T3b), então método com
  parâmetro sem anotação continua erro (`Parameter 'x' needs a type annotation.`). `init`
  idem.
- O retorno continua obrigatório (ADR-0020); T3c não infere retorno de `fn`.

### T4 — generalização de lambda em `val`

`val f = fn(...)` **sem tipo esperado** é inferido e generalizado:

1. parâmetros sem anotação viram `TyVar` frescas;
2. o retorno é inferido como em qualquer lambda (ou usa `-> T` se declarado);
3. as variáveis que continuam **livres** no tipo final viram o esquema (`GenericFnTy`).

```lox
val id = fn(x) => x
print id(1)      # Int
print id("a")    # String

val primeiro = fn(x, y) => x
print primeiro(10, 20)
print primeiro("z", "w")
```

- **Só `val`.** Com `var`, uma atribuição posterior poderia trocar a instância e quebrar o
  esquema; `var f = fn(x) => x` continua exigindo contexto/anotação.
- Sem variáveis livres (ex.: `val f = fn(x: Int) => x`), o tipo é um `FnTy` comum.
- Lambda com `-> T` declarado é checada contra ele, como antes.

### Função genérica não é valor (reforço)

`GenericFnTy` continua não sendo valor de primeira classe: `val g = f`, argumento e
`print f` dão erro. O guard de `print` passou a cobrir o caso — antes `print f` vazava e
imprimia `<fn>`.

## Limitações (honestas)

- **Corpo universal:** como no T3b, o corpo de função genérica só pode usar operações
  válidas para qualquer tipo — igualdade, `!= nil`, `is`, repasse. Aritmética (`x + 1`),
  truthiness e `len(x)` acusam erro porque `T` não é número/string. Constraints chegam no
  T6; sem elas, `fn dobro(x) -> Int { return x * 2 }` **não** compila.
- **Sem generalização fora de `val` de lambda direta** (ex.: `val fs = [fn(x) => x]` ou
  `val g = escolhe(fn(x) => x)`), e sem generalização de chamadas.
- **Sem type application explícita** e sem `T` em posição de chave de `Map` sem constraint.
- `val f = fn(x) => x` **não** torna `f` comparável/printável: é esquema, não valor.

## Consequências

- Funções utilitárias triviais (`igual`, `primeiro`, `id`) dispensam anotação de parâmetro.
- Bibliotecas podem expor `val id = fn(x) => x` e usar em vários tipos.
- O erro para `fn f(x) -> Int { return x }` vira `Expected Int, found T.` — informativo e
  no mesmo lugar do corpo.
- O backend (L2–L3) não é afetado: a linguagem apaga tipos; monomorfização é T7/L6.

## Alternativas rejeitadas

- **Unificar todos os parâmetros sem anotação no mesmo `T`:** impediria `igual(1, "a")` e
  surpreenderia; independência é mais previsível.
- **Generalizar `var`:** inseguro com mutação.
- **Inferir o retorno de `fn` também:** muda o contrato do ADR-0020 e a pré-declaração para
  recursão; fica para uma decisão própria (possivelmente junto do T6).
- **Hindley–Milner completo com generalização em toda expressão:** desproporcional; o
  let-polymorphism só em `val` cobre o caso de biblioteca.
