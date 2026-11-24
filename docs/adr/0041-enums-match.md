# ADR-0041 — Enums genéricos, `match` exaustivo e `Result`

- **Status:** accepted (implementado; padrões literais em [ADR-0140](0140-match-literais.md))
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0026](0026-freeze-1.0.md),
  [ADR-0027](0027-generics-t3b.md), [ADR-0031](0031-backend-nativo.md),
  [ADR-0039](0039-decisoes-tipos-pendentes.md),
  [ADR-0040](0040-generics-classes-desenho.md),
  [`../../TIPOS.md`](../../TIPOS.md), [`../../TODO.md`](../../TODO.md) §9

## Contexto

`T6c` é a última pendência do M5: `match`/enums e exaustividade. O `Result[T, E]`
(ADR-0039) depende de enum genérico; o codegen segue pausado no L4 até o M5 fechar.
O desenho precisa cobrir variantes com payload, `match` como expressão e checagem de
exaustividade sem transformar a linguagem num `match` estrutural geral.

## Decisões

1. **Enum genérico, variantes namespaced.** `enum Cor { Vermelho, Verde }` e
   `enum Shape { Circle(Float), Rect(Float, Float) }`; parâmetros `enum Result[T, E]`.
   Payload é **posicional**; variantes são acessadas como `Cor.Verde`,
   `Shape.Circle(1.0)`, `Result.Ok(1)` — nunca como nomes globais. `enum` é declarado no
   topo do programa.
2. **Tipos `EnumTy(name, args=())` e `EnumObjectTy(name)`.** `EnumTy` é o tipo do valor;
   `EnumObjectTy` é o namespace (`Cor`, `Result`). Argumentos são **invariantes**, como
   `ClassTy`/`List`/`Map`; `is`/`as` com argumentos são recusados (runtime apaga `T`).
3. **`match` é expressão.** `match e { Padrão => expr ... }`; arms separados por linha/`;`
   (sem vírgula obrigatória). Usar como statement é só descartar o resultado. Padrões da v1:
   `Nome.Variante`, `Nome.Variante(a, b)` (bindings posicionais) e `_` (curinga). Sem
   literais, guards, aninhamento, `|` ou `match` sobre uniões/`Any`.
4. **Exaustividade rígida.** O scrutinée precisa ser `EnumTy` (não `Any`/união); todas as
   variantes devem ser cobertas ou `_`; faltante é erro que lista as variantes; variante
   duplicada e arm depois de `_`/cobertura total são erro de arm inalcançável.
5. **`Result[T, E]` é enum embutido.** `Ok(T)` e `Err(E)`, sem métodos (`unwrap` etc.);
   `Option` continua sendo `T?`. `Result` é pré-declarado e não pode ser redefinido; o
   usuário escreve `Result[Int, String]`, `Result.Ok(1)`, `Result.Err("x")`.
6. **Semântica de valor.** Igualdade estrutural (enum, variante, payload com `==` da
   linguagem); `print Cor.Verde` → `Cor.Verde`, `print Shape.Circle(1.0)` →
   `Shape.Circle(1.0)`; sem ordenação, sem chave de `Map`, sem `len`.
7. **Backend.** `enum`, `match` e `EnumTy` são rejeitados com 65 até o L6; o layout
   (tag + payload) e a monomorfização ficam para o L6.

## Plano

1. Tokens/AST/parser: `enum`, `match`, padrões, `FAT_ARROW` (já existe), printer.
2. Tipos: `EnumTy`/`EnumObjectTy`, `display`, resolução/aridade, assignable/unify e
   substituição; `Result` embutido.
3. Checker: declaração de enum, construtores, `match` com bindings tipados, exaustividade
   e arms inalcançáveis.
4. Runtime: `LoxEnumObject`/`LoxEnumVariant`/`LoxEnumValue`, igualdade/stringify,
   `is`/`as` sem argumentos.
5. Testes/golden/docs e backend 65.

## Implementação (MVP)

Implementado: enums genéricos, variantes namespaced, `match` expressão com bindings e `_`,
exaustividade rígida, arms inalcançáveis, `Result` embutido, runtime/igualdade/stringify,
backend L6 e padrões literais ([ADR-0140](0140-match-literais.md)). O que resta está em
"Em aberto".

## Em aberto

- Guards, aninhamento, `|`, `match` sobre uniões/`Any`; padrões literais de `Float` ficam
  fora por decisão (ADR-0140).
- `is`/`as` com argumentos de enum (reificação) e métodos em enum.
- Monomorfização/layout no L6.

## Alternativas rejeitadas

- **Variantes globais (`Verde`/`Circle`)**: colidem com nomes e perdem o namespace.
- **`match` statement com `case:`**: não produz valor; `Result` ficaria desajeitado.
- **Exaustividade só em runtime/aviso**: contra I2 e o objetivo do T6c.
- **`Result` como classe genérica**: perde enum fechado e exaustividade.
- **Enums não genéricos primeiro**: adiaria `Result`; o custo de generics reusa o T6a.
