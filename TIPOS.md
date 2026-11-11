# TIPOS — catálogo e decisões de tipos da linguagem

Documento de design do sistema de tipos: o que suportar, como cada tipo se comporta e
quais decisões ainda estão **em aberto**. O foco principal continua sendo o modelo
numérico, porque ele condiciona o parser, o type checker, o interpretador e o backend
LLVM.

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

---

## 1. Catálogo de tipos

| Tipo | Sintaxe | Prioridade | Notas |
| --- | --- | --- | --- |
| `Nil` | `nil` | P0 | ausência de valor; tipo próprio, não "qualquer coisa" |
| `Bool` | `true` / `false` | P0 | nunca é número |
| `Int` | `42` | P0 | inteiro de 64 bits com sinal (ver §3 e ADR-0006) |
| `Float` | `3.14` | P0 | IEEE-754 binary64 (ver §3 e ADR-0006) |
| `String` | `"oi"` | P0 | UTF-8 imutável (ver §4) |
| `List[T]` | `[1, 2]` | P1 | mutável, indexada |
| `Map[K, V]` | `{ "a": 1 }` | P1 | sintaxe a decidir (colisão com bloco) |
| `Fn(P...) -> R` | `fn(a) -> a` | P1 | primeira classe, com closures |
| `Range` | `0..10` | P2 | iterável; ver §3.6 |
| `Tuple[A, B]` | `(1, "a")` | P2 | aridade fixa, destructuring |
| `Option[T]` | `T?` | P2 | alternativa a `nil` (ver §6) |
| `Result[T, E]` | `Result` | P3 | erros como valor (ver §6) |
| `Class` | `class P {}` | P2 | nominal, com herança ou traits (§8) |
| `Trait` | `trait Show` | P3 | structural/nominal a decidir |
| `Enum` / ADT | `enum Cor { Vermelho, ... }` | P3 | com `match` exaustivo |
| `Any` | `Any` | P1 | escape hatch; desliga checagem naquele ponto |
| `Never` | — | P2 | fundo: `throw`/`return`/loop infinito |

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

### 3.1 Literais: sufixos (`D-2`)

`1i64` e `1.0f32` **não** entram por enquanto. Bases, `_` e expoente já existem; sufixos
explícitos continuam sem decisão (provavelmente nunca, enquanto `Int` for sempre i64).

### 3.2 Divisão inteira `//` (`D-4`)

`//` colide com o comentário de linha: para existir, precisa de token próprio (`div`,
`\`) ou de trocar o comentário (`#`, ...). Até essa decisão, não há divisão inteira — só
`/` (Float) e `%` (truncado). O codegen deve emitir guarda de divisor ≠ 0 em
`sdiv`/`srem`, porque divisor zero é UB no LLVM.

### 3.3 Overflow checado no debug (`D-5`)

O padrão é wrapping (implementado). Quando houver codegen, um modo debug pode detectar
overflow e abortar: `llvm.sadd.with.overflow` no nativo e checagem equivalente no
interpretador, para os dois continuarem batendo.

### 3.4 Conversões e funções matemáticas (`D-8`)

```lox
let i = 3.9 as Int        // 3 (trunca em direção a zero)
let f = 3 as Float        // 3.0
let n = Int.parse("42")   // Result/Option, nunca crash silencioso
let s = 42.toString()     // "42"
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

### 3.5 Operadores bit a bit (`D-9`)

Só para `Int`, sem promoção (ainda **não implementado**):

```lox
a & b   // and
a | b   // or
a ^ b   // xor
~a      // not (complemento de 64 bits)
a << n  // shift left; n em [0, 63] senão erro (evita UB no LLVM)
a >> n  // shift aritmético (sinal); >>>
```

Precedência: a convenção C (`&` abaixo de `==`) é uma armadilha; adotar precedência
**toda acima de comparação** (como Rust) e registrar `D-9`.

### 3.6 Ranges (`D-10`)

```lox
0..10      // Range Int, fim exclusivo
0..=10     // Range Int, fim inclusivo
for i in 0..n { ... }
```

- Só `Int` no início (range de `Float` não tem passo natural) — `D-10`.
- `Range` é tipo próprio, iterável; `len(r)`, `contains`.
- `for i in 0..n` é o substituto do `for` C-style (§1.3 do TODO).
- Decidir se `..` cria lista (eager) ou é iterador preguiçoso: **iterador** (P2).

### 3.7 Inferência de tipos numéricos

Interação com o `TODO.md` §2 (T1–T7):

```lox
let a = 1          // Int
let b = 1.0        // Float
let c = 1 + 2.0    // Float (promoção)
let d = 1 / 2      // Float (D-4)
let e = 1.0 as Int // Int

fn metade(x) -> x / 2        // T := Int? Float? — ambíguo!
metade(4)                    // erro ou Float?
metade(4.0)
```

O caso `fn metade(x) -> x / 2` mostra o limite da inferência sem anotações: `/` força
`Float`, então `x` precisa ser `Float` — e a chamada com `4` (Int) promove. Regra:
**variáveis de tipo numéricas unificam com `Float` quando o corpo as usa em contexto
Float**; literais `Int` no argumento promovem. Documentar com exemplos no checker.

Regra de ouro: nunca deixar o tipo depender da ordem de avaliação; a unificação é
puramente estática. A relação `Int <: Float` vale para checagem, mas **não** para
variância: `List[Int]` não é `List[Float]` (mutação quebraria a segurança).

### 3.8 Mapeamento em LLVM (`D-11`)

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

### 3.9 Representação em runtime (`D-12`)

Ordem de evolução (detalhada no `TODO.md` §6.3):

1. **MVP**: valores boxeados `{ i8 tag, i64 payload }`; `Int` e `Float` com tags distintas.
2. **Otimização**: `Int`/`Float`/`Bool` desboxados quando o type checker conhece o tipo
   (monomorfização). `Any` permanece boxeado.
3. **Avançado**: NaN-boxing (payload em bits de `double`), reservando padrões para
   `nil`/`bool`/ponteiro; ~48 bits de ponteiro em x86-64.

### 3.10 Performance e benchmarks

`loop_sum` cobre laço com `Int`; falta um caso com `Float` para medir promoção/conversão
quando o modelo estabilizar. `Int` e `Float` em Python são objetos — o ganho real de
performance só vem com o backend nativo; no interpretador, o objetivo é **correção**, não
velocidade.

---

## 4. Strings e texto

- **UTF-8 imutável**, armazenada como bytes + length. Mutação gera nova string.
- `len(s)`: bytes (O(1)) ou code points (O(n))? **Decisão (`D-13`): `len` em code points**
  (menos surpresa para o usuário), com `byte_len` separado. Indexação `s[i]` por code
  point (O(n)) — aceitável no início, otimizar depois com cache.
- `s[i]` devolve `String` de 1 code point (não existe `Char`; evita um tipo novo).
- Concatenação `+`, comparação léxica `<`, `==` por conteúdo.
- Interpolação `"${expr}"` (TODO §1.3), escapes `\n \t \" \\ \u{...}`.
- `String.parse_int`/`to_int` devolvem `Option`/`Result`, nunca `NaN`/0 silencioso.
- Hash consistente com `==` — obrigatório para `Map[String, V]`.

---

## 5. Listas, mapas e tuplas

- `List[T]`: mutável, `push/pop/len`, indexação com checagem de limites (erro de runtime).
  Literal `[1, 2, 3]`; tipo inferido como `List[Int]` se todos os elementos unificam,
  senão `List[Any]` ou erro (decidir: homogêneo é mais seguro).
- `Map[K, V]`: chaves `String`/`Int`/`Bool` (hasháveis); literal `{ "a": 1 }` com
  ambiguidade de bloco a resolver (`#{...}` ou exigir `:` — `D-14`).
- `Tuple`: aridade fixa, imutável, destructuring; útil para múltiplos retornos.
- Variância: **invariante** por padrão (mutação); `List[Int]` não é `List[Float]`.

---

## 6. `nil`, `Option` e `Result`

- Hoje `nil` é um valor de qualquer tipo (dinâmico). Com tipos: `T?` opcional e
  **non-null por padrão** (Kotlin), `D-15`.
- `Option[T]` explícito + narrowing (`if x != nil`) é mais seguro que `nil` universal.
- `Result[T, E]` para erro recuperável; `throw` para erro excepcional. Não os dois para
  a mesma coisa.
- `Never` no fluxo (`return`/`throw`) evita falsos erros de tipo.

---

## 7. Funções

- Tipo: `fn(Int, String) -> Bool`; funções de primeira classe; closures.
- Parâmetros sem anotação viram variáveis de tipo (inferência na chamada, T3).
- Sem overloading por tipo no início (complica resolução e LLVM); usar nomes distintos
  ou traits.
- Retorno inferido quando o corpo é expressão (`fn dobro(x) -> x * 2`).
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

- `Any`: aceita tudo, desliga checagem (equivalente a `dynamic`); no LLVM, boxeado.
- `Never`: subtipo de todos; útil para `throw`/`return`/loop infinito.
- União `A | B`: P2/P3; narrowing obrigatório para usar.
- Aliases: `type UserId = Int` (P3).
- Sem tipos literais (`"foo"` como tipo) nem tipos dependentes.

---

## 10. Igualdade, hash e ordenação

Já implementado e descrito na spec: `Nil`, `Bool`, `Int`/`Float` (numérica com promoção,
`D-18`), `String` (conteúdo) e funções/classes/instâncias (identidade).

Em aberto:

- `List`: igualdade elemento a elemento (quando existir).
- `Map`: igualdade estrutural é inviável em geral; provavelmente identidade.
- Hash consistente com `==` para `Map[K, V]`: `1` e `1.0` precisam do mesmo hash se
  ambos puderem ser chave.
- Ordenação: `Int`/`Float`/`String`; `Bool` não ordenável.

---

## 11. Decisões em aberto

| Id | Decisão | Opções | Recomendação |
| --- | --- | --- | --- |
| `D-2` | sufixos de literal | `1i64` / `1.0f32` / não ter | não ter por enquanto |
| `D-4` | divisão inteira `//` | `div` / `\` / trocar comentário | decidir antes de usar |
| `D-5` | overflow no debug | checado / só wrapping | debug checado, release wrapping |
| `D-8` | conversões | `as` / funções | `as` + funções `math` |
| `D-9` | bitwise | precedência C vs Rust; shifts | Rust; shift inválido = erro |
| `D-10` | ranges | Int only / Float / passo | Int, iterador |
| `D-11` | LLVM | i64/double; guards | i64/double + guardas |
| `D-12` | representação | boxeado / desboxado / NaN-box | boxeado → desboxado |
| `D-13` | `len` de string | bytes / code points / graphemes | code points |
| `D-14` | literal de map | `{}` / `#{}` / outro | decidir antes de P1 |
| `D-15` | nullability | `T?` non-null / tudo anulável | non-null + `T?` |
| `D-16` | OO | herança / traits / ambos | herança simples primeiro |
| `D-17` | traits | nominal / estrutural | nominal |

Resolvidas: `D-1` (modelo `Int`+`Float`), `D-3` (promoção), `D-6` (formatação) e `D-18`
(igualdade numérica) — ver o checkbox no topo e
[ADR-0006](docs/adr/0006-int-float-separados.md). Cada decisão implementada ganha caso
golden e linha no `TODO.md` §11.

---

## 12. Roadmap por fases

| Fase | Entrega | Depende de |
| --- | --- | --- |
| **N0** | ✅ `Int` literal no lexer + `stringify` distinto + testes | nada |
| **N1** | 🟡 promoção `Int → Float`, `/` sempre `Float` e `%` truncado no interpretador; falta `//` (token) e bitwise | N0 |
| **N2** | sintaxe de anotação (`: Int`, `-> Float`) e `Ty` no AST | checker T1 |
| **N3** | unificação/checagem nas chamadas com promoção (T3) | N2 |
| **N4** | `as`, `math`, `Int.parse`, erros de conversão | N3 |
| **N5** | codegen LLVM de `Int`/`Float` com guards (L1/L6) | N4 + HIR |
| **N6** | ranges, `for-in` numérico | sintaxe §1.3 |

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
