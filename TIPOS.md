# TIPOS — catálogo e decisões de tipos da linguagem

Documento de design do sistema de tipos: o que suportar, como cada tipo se comporta e
quais decisões ainda estão **em aberto**. O foco é o que falta — iteração/coleções,
nullability, checker e mapeamento para LLVM.

Complementa:
- [`TODO.md`](TODO.md) §2 (estratégia de implementação da inferência: T1 → T7);
- [`TODO.md`](TODO.md) §6 (codegen / representação de valores em LLVM).

**Legenda:** `P0` agora · `P1` próximo · `P2` depois · `P3` algum dia
`S` horas · `M` dias · `L` semanas · `XL` meses

> Regra: decisão **em aberto** mora aqui, com id `D-n`; decisão implementada vira ADR e
> `docs/spec/`. O comportamento atual está em
> [`docs/spec/semantica.md`](docs/spec/semantica.md) — este arquivo não repete o que já
> funciona.

## Feito

- [x] **Números `Int` (i64) e `Float` (f64)** — literais (bases, `_`, expoente), promoção
  só `Int → Float`, `/` sempre `Float`, `%` truncado, wrapping, `stringify` distinguível
  e igualdade numérica (`1 == 1.0`). Ver
  [ADR-0006](docs/adr/0006-int-float-separados.md) e
  [`docs/spec/semantica.md`](docs/spec/semantica.md).
- [x] **Ranges e iteração** — `a..b` half-open, `range(a, b, step)`, `for-in` sobre
  Range/String e variável `val` por iteração. Ver
  [ADR-0007](docs/adr/0007-ranges-e-iteracao.md).
- [x] **Divisão inteira, potência e bits** — `//` truncado só `Int`, `**` (`Int`/`Float`),
  `& | ^ ~ << >> >>>` em i64, shifts com contagem `0..63`. Ver
  [ADR-0012](docs/adr/0012-comentarios-divisao-potencia-bits.md).
- [x] **Checagem estática gradual (T1/T2)** — anotações em funções, inferência local,
  `T?`/uniões, promoção e booleanos Python; `--check`. Ver
  [ADR-0010](docs/adr/0010-tipagem-estatica.md) e [`TODO.md`](TODO.md) §2.
- [x] **Ternário, `??` e `?.`** — união dos ramos; `??` remove `Nil`; `?.` produz
  `P | Nil` quando o objeto é anulável. Ver
  [ADR-0013](docs/adr/0013-ternario-nil-aware-escapes.md).
- [x] **Listas tipadas `List[T]`** — um tipo homogêneo e invariante, mutável in-place,
  literal `[1, 2]`, indexação/atribuição, `push`/`pop`, `len(xs)`, `for-in`, igualdade
  estrutural e `--check` com promoção numérica. Ver
  [ADR-0015](docs/adr/0015-listas-tipadas.md).

---

## 1. Catálogo de tipos

| Tipo | Sintaxe | Status | Prioridade | Notas |
| --- | --- | --- | --- | --- |
| `Nil` | `nil` | ✅ | P0 | ausência de valor; tipo próprio, não "qualquer coisa" |
| `Bool` | `true` / `false` | ✅ | P0 | nunca é número |
| `Int` | `42` | ✅ | P0 | inteiro de 64 bits com sinal (ver §3 e ADR-0006) |
| `Float` | `3.14` | ✅ | P0 | IEEE-754 binary64 (ver §3 e ADR-0006) |
| `String` | `"oi"` | ✅ | P0 | UTF-8 imutável (ver §4) |
| `List[T]` | `[1, 2]` | ✅ | P1 | homogênea, mutável e invariante; literais, indexação, `push`/`pop`, `len` e `for-in` (ADR-0015) |
| `Map[K, V]` | `{ "a": 1 }` | ✅ | P1 | homogêneo, mutável e invariante; literal, índice, `get`/`has`/`remove`/`keys`/`values`, `len` e `for-in` (ADR-0017) |
| `Fn(P...) -> R` | `fn(a) -> a` | 🟡 | P1 | funções existem; o tipo é inferido, sem sintaxe de anotação `fn(...)` |
| `Range` | `0..10` | ✅ | P2 | iterável; ver ADR-0007 |
| `Tuple[A, B]` | `(1, "a")` | ⬜ | P2 | aridade fixa, destructuring |
| `Option[T]` | `T?` | 🟡 | P1 | `T?` implementado; `Option[T]` como nome ainda não; non-null por padrão (`D-15`) |
| `Result[T, E]` | `Result` | ⬜ | P3 | erros como valor (ver §6) |
| `Class` | `class P {}` | ✅ | P2 | nominal, com herança ou traits (§8) |
| `Trait` | `trait Show` | ⬜ | P3 | structural/nominal a decidir |
| `Enum` / ADT | `enum Cor { Vermelho, ... }` | ⬜ | P3 | com `match` exaustivo |
| `Any` | `Any` | ✅ | P1 | escape hatch do checker; desliga a checagem naquele ponto |
| `Never` | — | 🟡 | P2 | interno do fluxo (`return`/loop); ainda sem `throw` público |

Legenda: **✅** existe no runtime e no checker · **🟡** existe só em parte (checker,
anotação ou runtime incompleto) · **⬜** ainda não implementado.

Tipos que **não** entram no curto prazo: `Complex`, `Rational`, `Decimal`, `UInt`,
`f32`, tipos dependentes, refinamentos. Ver §13.

---

## 2. Por que números primeiro

Números são o único tipo que aparece em **toda** camada:

- lexer precisa reconhecer literais e separadores;
- parser precisa decidir `1..10` (range) vs `1.0` (float);
- type checker precisa de promoção/coerção e de inferência de `1 + 2.0`;
- interpretador precisa de `stringify` estável (senão todo teste quebra);
- LLVM precisa mapear para `i64`/`double` e escolher instruções com semântica correta
  (`sdiv` é UB com divisor 0; `fcmp` tem variantes ordenadas/não ordenadas);
- igualdade/hash precisam ser consistentes entre `Int` e `Float` (`1 == 1.0`?).

Errar aqui custa refatorar o codegen inteiro. A parte implementada está no checkbox
acima; o que falta está nas seções seguintes.

---

## 3. Números — pendências e decisões abertas

Decisões já fechadas e implementadas — modelo `Int`/`Float` ([ADR-0006](docs/adr/0006-int-float-separados.md)),
`//` e bits ([ADR-0012](docs/adr/0012-comentarios-divisao-potencia-bits.md)) e
ranges/`for-in` ([ADR-0007](docs/adr/0007-ranges-e-iteracao.md)) — estão em
[`docs/decisoes.md`](docs/decisoes.md) e nos ADRs. Esta seção só lista o que ainda falta
decidir ou implementar.

### 3.1 Literais: sufixos (`D-2`)

`1i64` e `1.0f32` **não** entram por enquanto; sufixos explícitos continuam sem
decisão (provavelmente nunca, enquanto `Int` for sempre i64).

### 3.2 Overflow checado no debug (`D-5`)

Falta decidir se haverá um modo debug que detecta overflow e aborta, usando
`llvm.sadd.with.overflow` no nativo e checagem equivalente no interpretador para os dois
continuarem batendo. Esse modo ainda não existe.

### 3.3 Conversões e funções matemáticas (`D-8`)

> **Em aberto (ADR-0016):** `as` também é candidato a alias de import (estilo Python), então
> a sintaxe de cast e a API de parsing (`Int.parse` vs `to_int`/`parse_int`) continuam em
> aberto no [`TODO.md`](TODO.md) §11. O modelo híbrido não fecha essa parte.

Proposta ainda **não implementada**:

```lox
val i = 3.9 as Int        # 3 (trunca em direção a zero)
val f = 3 as Float        # 3.0
val n = Int.parse("42")   # Result/Option, nunca crash silencioso
val s = 42.toString()     # "42"
```

- `as` é cast **explícito** (sem exceção implícita) e verificado pelo checker quando
  possível.
- `Int(3.9)`/`Float("3.14")` como conversão: decidir função vs construtor (ver §8).
- `math`: `abs`, `min`, `max`, `floor`, `ceil`, `round`, `trunc`, `sqrt`, `pow`, `log`,
  `exp`, `sin`, `cos`, `tan`, `clamp`. `floor/ceil/round` devolvem **`Int`** (com erro se
  fora do range) ou `Float`? Recomendação: devolvem `Int` — é o que se quer para índices.
- `pow(Int, Int)` → `Int` com overflow wrapping? ou `Float`? Recomendação: `Float` para
  `**` e `math.pow`; `Int` só com expoente não negativo e via função explícita.
- `Int as Float` pode perder precisão acima de `2^53`; `Float as Int` exige checar
  `NaN`/`Inf` e o range de i64 antes de truncar.

### 3.4 Inferência pendente (`T3`/`T5`)

- **T3a (feito)** — assinaturas explícitas; funções de topo são pré-declaradas para que o
  corpo possa chamar funções declaradas depois (recursão mútua). Ver
  [ADR-0020](docs/adr/0020-assinaturas-explicitas.md).
- **T3b (feito, funções)** — `fn id[T](x: T) -> T` com unificação no call site; sem
  constraints, só operações universais; inferência apenas (sem `id[Int]`); monomorfização
  no backend. Classes/métodos genéricos ficam para depois. Ver
  [ADR-0027](docs/adr/0027-generics-t3b.md).
- **T3c (adiado)** — parâmetro sem anotação; depende de generalização (T4) e de uma regra
  explícita para não ficar monomórfico.
- **T5** — narrowing de `T?` em `if x != nil`/`if x == nil`/truthiness/early return já
  existe (ADR-0018); `is T`, `and`/`or` e `while` entraram no
  [ADR-0025](docs/adr/0025-is-e-narrowing.md); falta refinamento de campos/índices e merge
  completo de fluxo.

A regra de ouro continua: nunca deixar o tipo depender da ordem de avaliação; a checagem
é puramente estática. A relação `Int <: Float` vale para checagem, mas **não** para
variância: `List[Int]` não é `List[Float]` (mutação quebraria a segurança).

### 3.5 Mapeamento em LLVM (`D-11`)

| Conceito | IR | Observações |
| --- | --- | --- |
| `Int` | `i64` | `add`/`sub`/`mul` wrapping; `sdiv`/`srem` exigem guarda de divisor ≠ 0 |
| `Float` | `double` | `fadd`/`fsub`/`fmul`/`fdiv`; `fcmp olt`/`oeq` (ordenado) |
| `Bool` | `i1` (mask `0xFF`) ou i64 tag | decidir na representação de valor |
| literal | `Constant` | sem alocação |
| `Int → Float` | `sitofp` | seguro, pode perder precisão > 2^53 |
| `Float → Int` | `fptosi` | UB fora do range → checar `NaN`/limites antes |
| overflow checado | `llvm.sadd.with.overflow` | só no modo debug |
| `pow` | `llvm.pow.f64` / runtime para `Int` | |
| `min`/`max` | `llvm.smin`/`smax`/`fmin`/`fmax` | cuidado com `-0.0`/`NaN` |

**Nunca** emitir `sdiv` sem guarda: divisor zero = UB (pode crashar ou dar lixo).
**Nunca** converter `Float` → `Int` sem checar `is.finite` e range.

### 3.6 Representação em runtime (`D-12`)

Ordem de evolução (detalhada no `TODO.md` §6.3):

1. **L0–L2**: `Int`/`Float` concretos (i64/f64), strings/listas/mapas como ponteiros;
   `Any` é **rejeitado** no backend ([ADR-0026](docs/adr/0026-freeze-1.0.md)).
2. **Depois do MVP**: `Any` boxeado/tagged quando o backend ganhar representação dinâmica;
   monomorfização evita box nos caminhos concretos.
3. **Avançado**: NaN-boxing (payload em bits de `double`), reservando padrões para
   `nil`/`bool`/ponteiro; ~48 bits de ponteiro em x86-64.

### 3.7 Performance e benchmarks

`loop_sum` cobre laço com `Int`; falta um caso com `Float` para medir promoção/conversão
quando o modelo estabilizar. `Int` e `Float` em Python são objetos — o ganho real de
performance só vem com o backend nativo; no interpretador, o objetivo é **correção**, não
velocidade.

---

## 4. Strings e texto

- **UTF-8 imutável**, armazenada como bytes + length. Mutação gera nova string.
  Identificadores são ASCII na 1.0; strings aceitam Unicode
  ([ADR-0026](docs/adr/0026-freeze-1.0.md)).
- `len(s)`: bytes (O(1)) ou code points (O(n))? **Decisão (`D-13`): `len` em code points**
  (menos surpresa para o usuário), com `byte_len` separado. Indexação `s[i]` por code
  point (O(n)) fica para depois da 1.0 — hoje string não é indexável.
- `s[i]` devolve `String` de 1 code point (não existe `Char`; evita um tipo novo), quando
  entrar.
- Concatenação `+`, comparação léxica `<`, `==` por conteúdo.
- Interpolação `"${expr}"` (ADR-0019), com qualquer expressão convertida por `stringify`;
  escapes `\n \t \" \\ \$ \u{...}`.
- `String.parse_int`/`to_int` devolvem `Option`/`Result`, nunca `NaN`/0 silencioso.
- Hash consistente com `==` — obrigatório para `Map[String, V]`.

---

## 5. Listas, mapas e tuplas

- **`List[T]` (implementada)** — um tipo homogêneo, mutável in-place e **invariante**;
  literal `[1, 2, 3]`, indexação `xs[i]`, atribuição `xs[i] = v`, `xs.push(v)`,
  `xs.pop()`, `len(xs)` e `for x in xs`. Tipo inferido por unificação dos elementos
  (`[1, 2.0]` → `List[Float]`); mistura não numérica exige anotação explícita
  (`List[Int | String]` ou `List[Any]`). Lista vazia exige contexto. Índice é `Int`,
  zero-based, sem negativo; fora do intervalo é erro. Igualdade estrutural, sem hash
  (não pode ser chave de `Map`). Ver [ADR-0015](docs/adr/0015-listas-tipadas.md).
- **`Map[K, V]` (implementado)** — homogêneo, mutável in-place e invariante em `K`/`V`;
  literal `{"a": 1}` (chaves são expressões), `m[k]`/`m[k] = v`, `m.get(k)` (devolve `V?`),
  `m.has(k)`, `m.remove(k)`, `m.keys()`/`m.values()`, `len(m)` e `for k in m` (chaves em
  ordem de inserção). Chave ausente em `m[k]` é erro; `m.get(k) ?? default` cobre o caso
  opcional. Chaves são `String`, `Int` ou `Bool` (uniões explícitas permitidas); `Float`
  fica de fora até resolver `1 == 1.0`. Igualdade estrutural independente de ordem; mapas
  não são hasháveis. Ver [ADR-0017](docs/adr/0017-mapas-hash.md).
- `Tuple`: aridade fixa, imutável, destructuring; útil para múltiplos retornos.
- Variância: **invariante** por padrão (mutação); `List[Int]` não é `List[Float]` e
  `Map[String, Int]` não é `Map[String, Any]`. `Any` é escape explícito, não supertipo.

---

## 6. `nil`, `Option` e `Result`

- **Decidido (`D-15`)**: `Int` é non-null; `T?` é açúcar para `T | Nil` e aceita `nil`.
- **Mutação monomórfica**: `var x = nil` sem anotação é erro no `--check`; use `T?` ou
  `Any`. Variável não muda de tipo por atribuição; sem união implícita
  ([ADR-0024](docs/adr/0024-mutacao-monomorfica.md)).
- Ternário: tipo é `união(ramo1, ramo2)`; `??`: tipo é `non_nil(A) | B` (se `A` já é
  non-null, o tipo é `A`); `?.` em `T | Nil` produz `P | Nil`. Ver ADR-0013.
- Narrowing de fluxo (`if x != nil { ... }`, `if x == nil { return }`, `if x`) refina a
  união no checker (ADR-0018); `x is T` também refina, e `and`/`or`/`while` combinam
  (ADR-0025); `x or default` remove `Nil` via truthiness e `x ?? default` remove por nil.
  Campos/índices e merge completo de fluxo ainda faltam.
- `Option[T]` explícito, se necessário, será só açúcar/alias de `T?`; não duplicar os dois.
- `Result[T, E]` para erro recuperável; `throw` para erro excepcional. Não os dois para
  a mesma coisa.
- `Never` no fluxo (`return`/`throw`) evita falsos erros de tipo.

---

## 7. Funções

- Tipo: `fn(Int, String) -> Bool`; funções de primeira classe; closures.
- Parâmetros e retorno continuam **assinados**; generics explícitos de função já existem
  (`fn id[T]`), mas parâmetro sem anotação ainda é T3c/T4
  ([ADR-0020](docs/adr/0020-assinaturas-explicitas.md)).
- **Tipos de função nas anotações** já existem: `fn(Int) -> Int`, com variância
  (parâmetros contravariantes, retorno covariante) e classe como construtor
  ([ADR-0021](docs/adr/0021-tipos-de-funcao.md)).
- **Genéricos de função** existem: `fn map[T, U] (xs: List[T], f: fn(T) -> U) -> List[U]`.
  O corpo é checado uma vez, sem constraints; a chamada infere por unificação. Sem
  `id[Int](1)`, sem classes genéricas e sem função genérica como valor; monomorfização no
  backend ([ADR-0027](docs/adr/0027-generics-t3b.md)).
- **Lambdas** existem: `fn(x) => expr` / `fn(x) { ... }`, com tipagem contextual pelo tipo
  esperado e retorno inferido; mistura de retornos não-nil exige anotação
  ([ADR-0022](docs/adr/0022-lambdas.md)).
- Sem overloading por tipo no início (complica resolução e LLVM); usar nomes distintos
  ou traits.
- Retorno inferido em lambda (corpo de expressão ou bloco); funções declaradas ainda
  exigem `-> T` no `--check`.
- Erros/`throw` interagem com o tipo de retorno: `Never` no caminho que lança.

---

## 8. Classes, traits e enums

- Classes nominais, herança simples (ou traits — decisão `D-16`), `this`.
- Campos tipados, com default opcional.
- `enum` como ADT (variantes com payload) + `match` exaustivo (P3).
- Traits: nominal ou estrutural? Estrutural simplifica (`D-17`), mas colide com classes
  nominais; começar nominal.
- Conversão `Int`/`Float` como funções nativas ou construtores de classe? Preferir
  funções nativas (`to_int`, `to_float`) para não misturar modelo de objetos com primitivos.

---

## 9. Tipos especiais

- `Any`: aceita tudo, desliga checagem (equivalente a `dynamic`); no backend L0–L2 é
  rejeitado, e boxeado só quando a representação dinâmica entrar.
- `Never`: subtipo de todos; útil para `throw`/`return`/loop infinito.
- União `A | B`: implementada com narrowing de variáveis; `is T`, `and`/`or` e `while`
  funcionam; campos/índices e merge completo faltam.
- Aliases: `type UserId = Int` (P3).
- Sem tipos literais (`"foo"` como tipo) nem tipos dependentes.

---

## 10. Igualdade, hash e ordenação

Já implementado e descrito na spec: `Nil`, `Bool`, `Int`/`Float` (numérica com promoção,
`D-18`), `String` (conteúdo) e funções/classes/instâncias (identidade).

Em aberto:

- Hash de chave de `Map`: só `String`/`Int`/`Bool` na v1; `Float` fica de fora enquanto
  `1 == 1.0` não tiver uma regra de canonicalização (ADR-0017).
- Ordenação: `Int`/`Float`/`String`; `Bool` não ordenável.

Implementado: `List` compara **estruturalmente** (elemento a elemento, com guarda de
ciclo) e não é hashável; `Map` compara **estruturalmente, sem ordem** (com guarda de
ciclo), não é hashável e não pode ser chave; `nil`, `Bool`, `Int`/`Float`, `String` seguem
as regras acima.

---

## 11. Decisões em aberto

| Id | Decisão | Opções | Recomendação |
| --- | --- | --- | --- |
| `D-2` | sufixos de literal | `1i64` / `1.0f32` / não ter | não ter por enquanto |
| `D-5` | overflow no debug | checado / só wrapping | debug checado, release wrapping |
| `D-8` | conversões | `as` / funções | `as` + funções `math` |
| `D-11` | LLVM | i64/double; guards | i64/double + guardas |
| `D-12` | representação | boxeado / desboxado / NaN-box | boxeado → desboxado |
| `D-13` | `len` de string | bytes / code points / graphemes | code points |
| `D-16` | OO | herança / traits / ambos | herança simples primeiro |
| `D-17` | traits | nominal / estrutural | nominal |
| `D-19` | `List[T]` | um tipo / `List`+`MutableList` / `Array` | um tipo mutável e invariante (ADR-0015) |

Resolvidas: `D-1` (modelo `Int`+`Float`), `D-3` (promoção), `D-4` (divisão inteira),
`D-6` (formatação), `D-9` (bits), `D-10` (ranges/iteração), `D-14` (literal de mapa),
`D-15` (non-null + `T?`), `D-18` (igualdade numérica), `D-19` (List) e `D-20` (chaves de
`Map`) — ver os checkboxes no topo e os ADRs
[0006](docs/adr/0006-int-float-separados.md) /
[0007](docs/adr/0007-ranges-e-iteracao.md) /
[0010](docs/adr/0010-tipagem-estatica.md) /
[0012](docs/adr/0012-comentarios-divisao-potencia-bits.md) /
[0015](docs/adr/0015-listas-tipadas.md) /
[0017](docs/adr/0017-mapas-hash.md). Cada decisão implementada ganha caso golden e
resumo em [`docs/decisoes.md`](docs/decisoes.md); o que ainda está aberto fica no
`TODO.md` §11.

---

## 12. Roadmap por fases

| Fase | Entrega | Depende de |
| --- | --- | --- |
| **N0** | ✅ `Int` literal no lexer + `stringify` distinto + testes | nada |
| **N1** | ✅ promoção `Int → Float`, `/` sempre `Float`, `%`/`//` truncados, `**` e bitwise | N0 |
| **N2** | sintaxe de anotação (`: Int`, `-> Float`) e `Ty` no AST | checker T1 |
| **N3** | ✅ T3a + T3b (funções): assinaturas, pré-declaração e unificação; monomorfização no backend | N2 |
| **N4** | `as`, `math`, `Int.parse`, erros de conversão | N3 |
| **N5** | codegen LLVM de `Int`/`Float` com guards (L1/L6) | N4 + HIR |
| **N6** | ✅ ranges e `for-in` (Range/String/List/Map); `Map` implementado no ADR-0017 | sintaxe §1.1 |

Ordem prática: N2+ só depois do resolver (cap. 11), porque o checker depende de escopo.

---

## 13. Anti-metas (por enquanto)

- `Decimal`/fixed-point: só quando houver caso de uso real (dinheiro). Enquanto isso,
  documentar "use `Int` de centavos".
- `BigInt`: não. Overflow é wrapping; quem precisa de bignum usa biblioteca.
- `UInt` separado: não. `Int` cobre; bitwise opera em 64 bits.
- `f32`: não. `Float` é sempre `double`; `f32` só se GPU/SIMD entrar no escopo.
- `Complex`, `Rational`: não.
- Coerção implícita de string para número: **jamais** (a armadilha do JS).
- Comparação com epsilon: não; comparação é IEEE e ponto.

---

## 14. Referências

- Lox2 — tipos opcionais, `Int`/`Float` separados, uniões, erasure:
  <https://github.com/HallofFamer/Lox2> e `notes/TYPESYSTEM.md`.
- IEEE-754 (doubles, NaN, round-trip): <https://en.wikipedia.org/wiki/IEEE_754>
- Ryu/Grisu (formatação curta de float): <https://github.com/ulfjack/ryu>
- Rust `f64`/`i64` semânticas de divisão e overflow:
  <https://doc.rust-lang.org/reference/expressions/operator-expr.html>
- LLVM `sdiv`/`srem` UB: <https://llvm.org/docs/LangRef.html#sdiv-instruction>
- *Mapping High-Level Constructs to LLVM IR* (números e boxing):
  <https://mapping-high-level-constructs-to-llvm-ir.readthedocs.io/>
