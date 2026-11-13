# TIPOS — catálogo e decisões de tipos

O que a linguagem tem hoje, o que falta e quais decisões de tipo ainda estão abertas.
Comportamento observável fica em [`docs/spec/`](docs/spec/); decisões fechadas viram ADR +
[`docs/decisoes.md`](docs/decisoes.md). Este arquivo não repete o que já funciona.

> **Escopo:** o catálogo atual é o que existe na 1.0; as decisões em aberto e o roadmap
> são **pós-1.0**. Para o mapa 1.0 × depois, veja [`ESCOPO.md`](ESCOPO.md).

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
| `Any` | `Any` | ✅ | escape hatch; o backend L0–L3 o rejeita |
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

### 2.2 Pendente (T6/T7)

- **T6** — traits/protocolos e exaustividade de `match`.
- **T7** — monomorfização no codegen.

T6 fecha o **M5** (TODO §9); o codegen fica pausado no L4 até ele fechar — L5/L6 dependem
de layouts e monomorfização que só existem com tipos v2.

### 2.3 Performance

`loop_sum` cobre laço com `Int`; falta um caso `Float` quando o modelo estabilizar. No
interpretador o objetivo é correção; ganho real vem do backend.

## 3. Strings e texto

Sem decisões de tipo em aberto: decisões e comportamento estão no
[ADR-0035](docs/adr/0035-strings-texto.md) e em
[`docs/spec/semantica.md`](docs/spec/semantica.md). Fora deste catálogo: strings
multilinha/raw (TODO §1) e builtins de string (stdlib).

## 4. Tuplas

Sintaxe e semântica decididas ([ADR-0030](docs/adr/0030-tuplas.md)); implementação
pós-1.0/backend. **Em aberto**, para decidir junto da implementação:

- `for x in t` — elementos heterogêneos; iterar exige a união dos tipos ou recusa.
- `is (A, B)` — checagem por posição em tempo de execução.

## 5. `nil`, `Option` e `Result`

- `T?` é açúcar para `T | Nil`; non-null por padrão (`D-15`); mutação monomórfica
  ([ADR-0024](docs/adr/0024-mutacao-monomorfica.md)).
- Narrowing de `T?`, `is T`, `and`/`or` e `while` funcionam, inclusive **campos e índices
  literais** (`p.nome`, `xs[0]`, `m["k"]`), com invalidação ao mutar o caminho/raiz e refino
  pós-laço ([ADR-0018](docs/adr/0018-narrowing.md), [ADR-0025](docs/adr/0025-is-e-narrowing.md),
  [ADR-0032](docs/adr/0032-narrowing-campos-indices.md)); faltam CFG/aliasing.
- `Option[T]` explícito, se existir, é alias de `T?`; não duplicar.
- `Result[T, E]` para erro recuperável; `throw` excepcional; não os dois para a mesma coisa.
- `Never` no fluxo evita falsos erros.

## 6. Funções

- Tipo `fn(Int, String) -> Bool`; primeira classe; closures ([ADR-0021](docs/adr/0021-tipos-de-funcao.md)).
  No backend, hoje só existem funções de topo chamadas diretamente (L2); função como valor
  e closures chegam no L4, depois do M5.
- Parâmetros/retorno assinados; generics de função T3b ([ADR-0027](docs/adr/0027-generics-t3b.md));
  `val f = fn(x) => x` generaliza (T4) ([ADR-0033](docs/adr/0033-inferencia-t3c-t4.md)),
  mas parâmetro de `fn` continua exigindo anotação (T3c rejeitado,
  [ADR-0034](docs/adr/0034-t3c-revertido.md)); o corpo genérico só usa operações
  universais.
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

- `Any`: aceita tudo, desliga checagem; backend L0–L3 rejeita; boxeado só depois.
- `Never`: subtipo de todos; útil para `throw`/`return`/loop.
- União `A | B`: implementada; falta merge em CFG/aliasing (ver [ADR-0032](docs/adr/0032-narrowing-campos-indices.md)).
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
| `D-17` | traits | nominal / estrutural | nominal |

Fechadas: todas exceto `D-2` e `D-17` — ver ADRs e
[`docs/decisoes.md`](docs/decisoes.md). `D-5`/`D-8` saíram daqui: implementados em
[ADR-0028](docs/adr/0028-overflow-debug.md)/[ADR-0029](docs/adr/0029-conversoes-math.md).

## 11. Roadmap pendente

| Fase | Entrega |
| --- | --- |
| **N6+** | tuplas, traits/enums, `Result`/`Option` explícito e stdlib |

N0–N5 (números, anotações, T3/T4/T5 e codegen desboxado de `Int`/`Float`/`String`) estão
fechados.

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
