# ADR-0024 — Mutação monomórfica e `var x = nil`

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0018](0018-narrowing.md), [ADR-0023](0023-soundness-do-checker.md),
  [`../../TODO.md`](../../TODO.md) §11, [`../../TIPOS.md`](../../TIPOS.md) §6,
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/checker.py`](../../src/checker.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

A decisão 13 do `TODO.md` estava aberta: o que fazer com

```lox
var x = nil
x = 1
```

O checker inferia `x: Nil` e depois recusava a atribuição com
`Expected Nil, found Int.` — uma mensagem longe da causa e um tipo inútil para a variável.
As alternativas eram inferir união, inferir `Any` ou exigir anotação.

Para o codegen, variável monomórfica é muito mais simples: cada slot tem um tipo e um
layout; união/`Any` forçam boxing ou uma representação dinâmica em todo o fluxo.

## Decisão

1. **Bindings são monomórficos no `--check`.** `var x = 1` é `Int` para sempre; `x = 2`
   é permitido; `x = 2.0` é erro (`Expected Int, found Float.`). Não há inferência de união
   nem promoção de tipo da variável por atribuição.
2. **`var x = nil` sem anotação é erro de compilação:**

   ```lox
   var x = nil
   # Can't infer type of 'x' from nil; add an annotation.
   ```

   O usuário escreve o tipo:

   ```lox
   var x: Int? = nil
   x = 1
   x = nil
   ```

   ou `var x: Any = nil` para o escape dinâmico.
3. **Campo mutável com inicializador `nil` segue a mesma regra:**

   ```lox
   class C {
     var x = nil          # erro: Field 'x' initialized with nil needs a type annotation.
   }
   ```

   `var x: Int? = nil` e `var x: Any = nil` funcionam.
4. **`val x = nil` é permitido.** O binding é imutável; o tipo `Nil` não cria expectativa de
   receber outro valor. O mesmo vale para campo `val = nil`.
5. **Atribuição usa o tipo declarado.** `Int → Float` continua permitido pela promoção
   existente; `Float → Int` não. A anotação `T?` mantém a união, e o narrowing de fluxo
   continua sendo o mecanismo para usá-la como `T`.
6. **Sem `flow-sensitive` para variáveis.** O tipo não muda conforme atribuições no fluxo;
   para isso existem anotação, `is T` (futuro) e narrowing.

## Consequências

### Positivas

- Erro no ponto da declaração, não na atribuição distante.
- Variável tem um tipo único e estável; codegen pode reservar slot/layout direto.
- Sem união implícita e sem `Any` silencioso: o escape é explícito.
- `var x: Int? = nil; x = 1` cobre o caso comum com uma anotação curta.
- Consistente com `var x;` sem inicializador, que já exigia anotação.

### Negativas / custos

- `var x = nil; x = 1` deixa de ser “só funciona”; exige `: Int?` ou `: Any`.
- `var x = 1; x = 2.0` é recusado; quem quer os dois precisa anotar `Float` ou `Any`.
- Sem inferência de união por fluxo, padrões como “começa nil, vira T” pedem anotação.
- `val x = nil` continua permitido, mas é um tipo `Nil` quase inútil; é inofensivo.
- A promoção `Int → Float` na atribuição ainda é apagada em runtime (limitação conhecida do
  tree-walk; o LLVM converteria).

## Alternativas consideradas

| Alternativa | Por que não agora |
| --- | --- |
| Inferir `Int \| Nil` para `var x = nil` | Union implícita contamina o tipo e complica codegen; o usuário pode escrever a união |
| Inferir `Any` para `var x = nil` | Desliga a checagem em silêncio; contra o I2 e o ideal de tipos explícitos |
| Flow-sensitive (`x` muda de tipo por atribuição) | Mais caro e difícil de casar com LLVM/SSA; fica para depois de narrowing completo |
| Proibir `var` sem inicializador e sem anotação | Já é o comportamento atual; a decisão fecha a regra |
| Proibir `val x = nil` também | Não há mutação nem expectativa de outro tipo; seria cerimônia sem ganho |

## Como verificar

- `tests/test_checker.py`:
  - `test_var_initialized_with_nil_needs_annotation`;
  - `test_var_nil_with_annotation_can_receive_values`;
  - `test_var_nil_with_any_annotation_allows_any_value`;
  - `test_mutable_var_is_monomorphic`;
  - `test_val_initialized_with_nil_is_allowed`;
  - `test_mutable_field_initialized_with_nil_needs_annotation`;
  - `test_immutable_field_initialized_with_nil_is_allowed`;
- `make check` verde.

Critério para revisar: quando `is T`/flow-sensitive para `val` entrarem, ou se a exigência
de anotação em `var x = nil` incomodar em código real.
