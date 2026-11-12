# TIPOS — catálogo e decisões de tipos

O que a linguagem tem hoje, o que falta e quais decisões de tipo ainda estão abertas.
Comportamento observável fica em [`docs/spec/`](docs/spec/); decisões fechadas viram ADR +
[`docs/decisoes.md`](docs/decisoes.md). Este arquivo não repete o que já funciona.

**Legenda:** `P0` agora · `P1` próximo · `P2` depois · `P3` algum dia
`S` horas · `M` dias · `L` semanas · `XL` meses

> Decisão em aberto mora aqui com id `D-n`. Quando fecha, sai daqui e vira ADR; o resumo
> executivo fica em [`docs/decisoes.md`](docs/decisoes.md).

## 1. Catálogo atual

| Tipo | Sintaxe | Status | Notas |
| --- | --- | --- | --- |
| `Nil` | `nil` | ✅ | ausência de valor; tipo próprio, não "qualquer coisa" |
| `Bool` | `true` / `false` | ✅ | nunca é número |
| `Int` | `42` | ✅ | i64 com sinal; wrapping no release, erro no `--debug` |
| `Float` | `3.14` | ✅ | IEEE-754 binary64 |
| `String` | `"oi"` | ✅ | UTF-8 imutável; `len` em code points, sem indexação |
| `List[T]` | `[1, 2]` | ✅ | homogênea, mutável e invariante ([ADR-0015](docs/adr/0015-listas-tipadas.md)) |
| `Map[K, V]` | `{ "a": 1 }` | ✅ | homogêneo, mutável e invariante; chaves `String`/`Int`/`Bool` ([ADR-0017](docs/adr/0017-mapas-hash.md)) |
| `Fn(P...) -> R` | `fn(Int) -> Bool` | ✅ | anotação, variância e lambdas ([ADR-0021](docs/adr/0021-tipos-de-funcao.md), [ADR-0022](docs/adr/0022-lambdas.md)) |
| `Range` | `0..10` | ✅ | half-open, lazy ([ADR-0007](docs/adr/0007-ranges-e-iteracao.md)) |
| `Class` | `class P {}` | ✅ | nominal, herança simples ([ADR-0008](docs/adr/0008-heranca-class-parens.md)) |
| `Any` | `Any` | ✅ | escape hatch; o backend L0–L2 o rejeita |
| `Never` | — | 🟡 | interno de fluxo (`return`/loop); sem `throw` público |
| `Tuple` | `(1, "a")` / `(A, B)` | ⬜ | sintaxe no [ADR-0030](docs/adr/0030-tuplas.md), implementação pós-1.0 |
| `Trait` | `trait Show` | ⬜ | nominal ou estrutural a decidir (`D-17`) |
| `Enum`/ADT | `enum Cor { ... }` | ⬜ | com `match` exaustivo (P3) |
| `Result[T, E]` | `Result` | ⬜ | erros como valor (P3) |

Fora do curto prazo: `Complex`, `Rational`, `Decimal`, `UInt`, `f32`, tipos dependentes e
refinamentos.

## 2. Números — o que falta

O modelo `Int`/`Float` está fechado ([ADR-0006](docs/adr/0006-int-float-separados.md)):
promoção só `Int → Float`, `/` sempre `Float`, `%` truncado, `//` só `Int`, i64 wrapping,
`--debug` checando overflow ([ADR-0028](docs/adr/0028-overflow-debug.md)).

### 2.1 Sufixos de literal (`D-2`)

`1i64` e `1.0f32` continuam sem decisão; provavelmente nunca, enquanto `Int` for i64.

### 2.2 Inferência pendente (`T3`/`T5`)

- **T3c** — parâmetro sem anotação; depende de generalização (T4) e de regra explícita
  para não ficar monomórfico.
- **T4** — let-polymorphism para funções genéricas implícitas.
- **T5** — narrowing restante: campos/índices e merge completo de fluxo.
- **T6** — traits/protocolos e exaustividade de `match`.
- **T7** — monomorfização no codegen.

### 2.3 Mapeamento em LLVM (`D-11`)

| Conceito | IR | Observações |
| --- | --- | --- |
| `Int` | `i64` | `add`/`sub`/`mul` wrapping; `sdiv`/`srem` exigem guarda |
| `Float` | `double` | `fadd`/`fsub`/`fmul`/`fdiv`; `fcmp` ordenado |
| `Bool` | `i1` ou tag i64 | decidir na representação de valor |
| `Int → Float` | `sitofp` | pode perder precisão > 2^53 |
| `Float → Int` | `fptosi` | UB fora do range; checar `NaN`/limites |
| overflow checado | `llvm.sadd.with.overflow` | só `--debug` |
| `min`/`max` | `llvm.smin`/`smax`/`fmin`/`fmax` | cuidado com `-0.0`/`NaN` |

Nunca emitir `sdiv` sem guarda; nunca converter `Float` para `Int` sem checar finite/range.

### 2.4 Representação em runtime (`D-12`)

1. **L0–L2:** `Int`/`Float` concretos (i64/f64), strings/listas/mapas como ponteiros;
   `Any` rejeitado ([ADR-0026](docs/adr/0026-freeze-1.0.md)).
2. **Depois do MVP:** `Any` boxeado/tagged; monomorfização evita box nos caminhos concretos.
3. **Avançado:** NaN-boxing, se houver necessidade real.

### 2.5 Performance

`loop_sum` cobre laço com `Int`; falta um caso `Float` quando o modelo estabilizar. No
interpretador o objetivo é correção; ganho real vem do backend.

## 3. Strings e texto

- UTF-8 imutável, bytes + length; identificadores ASCII na 1.0, strings Unicode
  ([ADR-0026](docs/adr/0026-freeze-1.0.md)).
- `len(s)` em **code points** (`D-13`); indexação `s[i]` por code point fica para depois
  da 1.0 — hoje string não é indexável.
- `s[i]` devolveria `String` de 1 code point (sem tipo `Char`), quando entrar.
- Concatenação `+`, comparação léxica `<`, `==` por conteúdo; interpolação
  ([ADR-0019](docs/adr/0019-interpolacao.md)).
- Parse é `Int.parse`/`Float.parse` → `T?` ([ADR-0029](docs/adr/0029-conversoes-math.md));
  não existe `String.to_int`.
- Hash consistente com `==` para chave de `Map[String, V]`.

## 4. Listas, mapas e tuplas

- **`List[T]`** — homogênea, mutável in-place e invariante; literal, índice/atribuição,
  `push`/`pop`, `len`, `for-in`, igualdade estrutural; lista vazia exige contexto
  ([ADR-0015](docs/adr/0015-listas-tipadas.md)).
- **`Map[K, V]`** — homogêneo, mutável e invariante; `m[k]` erra se ausente, `m.get(k)`
  devolve `V?`; `has`/`remove`/`keys`/`values`; iteração de chaves em ordem de inserção;
  igualdade estrutural sem ordem; não é hashável ([ADR-0017](docs/adr/0017-mapas-hash.md)).
- **`Tuple`** — aridade 2+, imutável, `t[0]` e destructuring `val (a,b) = t`; implementação
  pós-1.0/backend ([ADR-0030](docs/adr/0030-tuplas.md)).
- Variância: invariante (`List[Int]` não é `List[Float]`); `Any` é escape explícito, não
  supertipo.

## 5. `nil`, `Option` e `Result`

- `T?` é açúcar para `T | Nil`; non-null por padrão (`D-15`); mutação monomórfica
  ([ADR-0024](docs/adr/0024-mutacao-monomorfica.md)).
- Narrowing de `T?`, `is T`, `and`/`or` e `while` funcionam ([ADR-0018](docs/adr/0018-narrowing.md),
  [ADR-0025](docs/adr/0025-is-e-narrowing.md)); faltam campos/índices e merge completo.
- `Option[T]` explícito, se existir, é alias de `T?`; não duplicar.
- `Result[T, E]` para erro recuperável; `throw` excepcional; não os dois para a mesma coisa.
- `Never` no fluxo evita falsos erros.

## 6. Funções

- Tipo `fn(Int, String) -> Bool`; primeira classe; closures ([ADR-0021](docs/adr/0021-tipos-de-funcao.md)).
- Parâmetros/retorno assinados; generics de função T3b ([ADR-0027](docs/adr/0027-generics-t3b.md));
  parâmetro sem anotação é T3c/T4.
- Sem overloading por tipo; usar nomes distintos ou traits.
- Retorno inferido em lambda; funções declaradas exigem `-> T` no `--check`.
- `throw` interage com `Never` no caminho que lança.

## 7. Classes, traits e enums

- Classes nominais, herança simples, `this` ([ADR-0008](docs/adr/0008-heranca-class-parens.md)).
- Campos tipados com default opcional.
- `enum` como ADT + `match` exaustivo (P3).
- Traits: nominal ou estrutural? (`D-17`); começar nominal.
- Conversões são `as`/`Int.parse` ([ADR-0029](docs/adr/0029-conversoes-math.md)); não há
  `to_int`/`to_float`.

## 8. Tipos especiais

- `Any`: aceita tudo, desliga checagem; backend L0–L2 rejeita; boxeado só depois.
- `Never`: subtipo de todos; útil para `throw`/`return`/loop.
- União `A | B`: implementada com narrowing de variáveis; faltam campos/índices e merge.
- Aliases `type UserId = Int` (P3); sem tipos literais nem dependentes.

## 9. Igualdade, hash e ordenação

Atual: `Nil`, `Bool`, `Int`/`Float` (numérica, `D-18`), `String` (conteúdo),
funções/classes/instâncias (identidade), `List`/`Map` (estrutural; não hasháveis).

Em aberto:
- Chave de `Map`: só `String`/`Int`/`Bool`; `Float` fica fora enquanto `1 == 1.0` não tiver
  canonicalização ([ADR-0017](docs/adr/0017-mapas-hash.md)).
- Ordenação: `Int`/`Float`/`String`; `Bool` não ordenável.

## 10. Decisões em aberto

| Id | Decisão | Opções | Recomendação |
| --- | --- | --- | --- |
| `D-2` | sufixos de literal | `1i64` / `1.0f32` / não ter | não ter por enquanto |
| `D-11` | LLVM | i64/double; guards | i64/double + guardas |
| `D-12` | representação | boxeado / desboxado / NaN-box | desboxado; `Any` depois |
| `D-13` | `len` de string | bytes / code points / graphemes | code points |
| `D-16` | OO | herança / traits / ambos | herança simples primeiro |
| `D-17` | traits | nominal / estrutural | nominal |

Fechadas: `D-1`–`D-10`, `D-14`, `D-15`, `D-18`–`D-20` — ver ADRs e
[`docs/decisoes.md`](docs/decisoes.md). `D-5`/`D-8` saíram daqui: implementados em
[ADR-0028](docs/adr/0028-overflow-debug.md)/[ADR-0029](docs/adr/0029-conversoes-math.md).

## 11. Roadmap pendente

| Fase | Entrega |
| --- | --- |
| **N5** | codegen LLVM de `Int`/`Float` com guards (L1/L6) |
| **N6+** | tuplas, traits/enums, `Result`/`Option` explícito e stdlib |

N0–N4 (números, anotações, T3a/T3b e D-8) estão fechados.

## 12. Anti-metas

- `Decimal`/fixed-point: só com caso de uso real (dinheiro); por ora, `Int` de centavos.
- `BigInt`: não; overflow é wrapping no release e erro no `--debug`.
- `UInt` separado: não; `Int` cobre e bitwise opera em 64 bits.
- `f32`: não; `Float` é sempre `double`.
- `Complex`/`Rational`: não.
- Coerção implícita string↔número: jamais.
- Comparação com epsilon: não; comparação é IEEE.

## 13. Referências

- Lox2 — tipos opcionais, `Int`/`Float`, uniões, erasure:
  <https://github.com/HallofFamer/Lox2>.
- IEEE-754: <https://en.wikipedia.org/wiki/IEEE_754>.
- Ryu/Grisu: <https://github.com/ulfjack/ryu>.
- Rust `f64`/`i64` e overflow:
  <https://doc.rust-lang.org/reference/expressions/operator-expr.html>.
- LLVM `sdiv`/`srem`: <https://llvm.org/docs/LangRef.html#sdiv-instruction>.
