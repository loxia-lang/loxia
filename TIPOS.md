# TIPOS — catálogo e decisões de tipos da linguagem

Documento de design do sistema de tipos: o que suportar, como cada tipo se comporta e
quais decisões ainda estão abertas. O **foco principal é o modelo numérico**, porque ele
condiciona o parser, o type checker, o interpretador e o backend LLVM.

Complementa:
- [`TODO.md`](TODO.md) §2 (estratégia de implementação da inferência: T1 → T7);
- [`TODO.md`](TODO.md) §6 (codegen / representação de valores em LLVM).

**Legenda:** `P0` agora · `P1` próximo · `P2` depois · `P3` algum dia
`S` horas · `M` dias · `L` semanas · `XL` meses

> Regra: este arquivo é o **contrato semântico**. Se o comportamento de um tipo mudar,
> a decisão muda aqui primeiro, com o motivo. Cada decisão tem um id (`D-n`) citável
> em commits e no `TODO.md`.

> **Estado atual do código:** `Int` (i64) e `Float` (f64) já estão separados no tree-walk —
> literais (incl. `_` e bases), promoção `Int → Float`, `/` sempre `Float`, `%` truncado,
> wrapping e `stringify` distinto ([ADR-0006](docs/adr/0006-int-float-separados.md)).
> Ainda **não** existem: `//` (colide com comentário), bitwise, `as`/conversões, `math`,
> type checker e codegen. As decisões deste documento continuam sendo o contrato.

---

## 1. Catálogo de tipos

| Tipo | Sintaxe | Prioridade | Notas |
| --- | --- | --- | --- |
| `Nil` | `nil` | P0 | ausência de valor; tipo próprio, não "qualquer coisa" |
| `Bool` | `true` / `false` | P0 | nunca é número |
| `Int` | `42` | P0 | inteiro de 64 bits com sinal (ver §3) |
| `Float` | `3.14` | P0 | IEEE-754 binary64 (ver §3) |
| `String` | `"oi"` | P0 | UTF-8 imutável (ver §4) |
| `List[T]` | `[1, 2]` | P1 | mutável, indexada |
| `Map[K, V]` | `{ "a": 1 }` | P1 | sintaxe a decidir (colisão com bloco) |
| `Fn(P...) -> R` | `fn(a) -> a` | P1 | primeira classe, com closures |
| `Range` | `0..10` | P2 | iterável; ver §3.10 |
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

Errar aqui custa refatorar o codegen inteiro. Por isso as decisões `D-N` abaixo.

---

## 3. Números

### 3.1 Decisão central: um `Number` ou `Int` + `Float`?

| Opção | Prós | Contras |
| --- | --- | --- |
| **`Number` único (double)**, como o Lox do livro | simples; uma tag; aritmética trivial | perde exatidão > 2^53; índices/bitwise exigem conversão; LLVM sempre `double` ou boxeado; `1` não é distinguível de `1.0` |
| **`Int` + `Float` separados**, como Lox2/Rust/C | `i64` exato para índices/contadores; operações de inteiro no LLVM sem boxing; bitwise natural; performance | precisa de regras de promoção e de conversão explícita; `stringify` tem que distinguir; mais trabalho no checker |
| `Int` + `Float` + `Decimal` | dinheiro correto | escopo e runtime muito maiores |

**Recomendação (`D-1`): `Int` (i64) + `Float` (f64), com promoção implícita `Int → Float`
e nenhuma conversão implícita no sentido contrário.** O Lox2 fez essa separação e a
experiência mostra que o atrito é pequeno se as regras forem explícitas.

Isso muda a semântica atual do Lox (tudo é `float`). A migração é faseada:

1. lexer passa a emitir `int` para literais sem `.`/expoente e `float` para o resto;
2. interferência mínima: `stringify` já distingue (`1` vs `1.0` — ver `D-7`);
3. checker só começa a impor regras quando existir (`TODO.md` §2);
4. interpretador continua aceitando os dois e promovendo em tempo de execução.

### 3.2 Literais (`D-2`)

```lox
0          // Int
42         // Int
1_000_000  // Int (separador _ é açúcar sintático; ignorado no valor)
0xFF       // Int = 255
0b1010     // Int = 10
0o755      // Int = 493
3.14       // Float
0.5        // Float
1e9        // Float = 1000000000.0
1.5e-3     // Float = 0.0015
1.0        // Float (e não Int)
```

Regras propostas:

- `_` permitido em qualquer posição entre dígitos, nunca no começo/fim (`1__0` inválido).
- `0x`/`0b`/`0o` **não** aceitam ponto nem expoente.
- Sufixos explícitos (`1i64`, `1.0f32`) **não** por enquanto — `D-2` deixa aberto.
- `.5` e `1.` **não**: exigir dígito dos dois lados do ponto (igual ao scanner atual).
  Evita ambiguidade com `..` de range e com acesso a membro.
- `1..10` é range, não float: o scanner precisa ver `.` seguido de `.` antes de decidir
  (já é o caso no scanner atual, que exige dígito depois do ponto).
- Overflow de literal: `999999999999999999999` é erro de compilação ("literal inteiro
  grande demais"), não vira `Float` silenciosamente.
- Implementação atual: a magnitude máxima do literal é `2^63 - 1`; `INT_MIN` não tem
  literal próprio — use aritmética (`-9223372036854775807 - 1`).

### 3.3 Promoção e coerção (`D-3`)

| Expressão | Resultado | Regra |
| --- | --- | --- |
| `Int op Int` | `Int` | exceto `/` (ver §3.4) |
| `Int op Float` | `Float` | promove o `Int` (seguro) |
| `Float op Int` | `Float` | idem |
| `Float op Float` | `Float` | |
| atribuição `let f: Float = 1` | ok | literal `Int` promove no contexto `Float` |
| atribuição `let i: Int = 1.5` | **erro** | nunca trunca implicitamente |
| `let i: Int = f` (var `Float`) | **erro** | exige `as Int` explícito |
| argumento `fn f(x: Float)` chamado com `1` | ok | literal promove |
| `fn f(x: Int)` chamado com `f2` (`Float`) | **erro** | exige `as Int` |

Regra de bolso: **promoção só para cima (`Int → Float`) e só quando não perde
informação.** Float→Int é sempre explícito (`as Int`), com semântica truncada (em
direção a zero), e `NaN`/`Inf` são erro de runtime.

Isso implica uma relação de subtipagem numérica `Int <: Float` para checagem. Cuidado
com variância de `List` (§5): `List[Int]` **não** é `List[Float]` (mutação quebraria a
segurança).

### 3.4 Divisão, módulo e resto (`D-4`)

O ponto onde linguagens mais divergem:

| Operador | Proposta | Por quê |
| --- | --- | --- |
| `/` entre `Int` | **`Float`** (ex.: `1 / 2 == 0.5`) | `1/2 == 0` é a armadilha nº 1 de C/Rust/Go; errar aqui gera bug silencioso |
| `//` entre `Int` | `Int`, truncado em direção a zero | divisão inteira explícita |
| `%` entre `Int` | resto com sinal do dividendo (truncado) | casa com `srem` do LLVM; `-7 % 3 == -1` |
| `%` entre `Float` | `fmod` (sinal do dividendo) | consistente com `Int` |
| divisão por zero | **erro de runtime** para `Int` e `Float` | determinístico e testável; evita `NaN`/`inf` vazando (decisão atual mantida) |

Alternativa rejeitada: `%` com sinal do divisor (estilo Python, `-7 % 3 == 2`). É ótimo
para aritmética modular, mas surpreende quem vem de C/JS e não casa com `srem`.
Se `mod` matemático for necessário, criar função `math.mod(a, b)` depois.

**Pendência (`//`)**: em Lox `//` já significa **comentário de linha**. Usar `//` como
divisão inteira exige outra sintaxe (`div`, `\`) ou trocar o comentário — decisão
separada. Por isso `//` não existe no interpretador hoje; só `%` foi implementado.

Notas de codegen:
- `sdiv`/`srem` do LLVM são **UB com divisor zero** → o codegen precisa emitir um `icmp`
  + branch para o runtime de erro. Nunca confie no hardware.
- Divisão inteira de `INT_MIN / -1` também é UB em LLVM; tratar como overflow (ou erro).

### 3.5 Overflow e precisão (`D-5`)

- `Int` é `i64` com sinal. Operações **wrapping** no release (padrão do LLVM).
- O interpretador em Python deve **simular** o wrapping (`((a+b+2**63) % 2**64) - 2**63`)
  para o oráculo bater com o nativo. Sem isso, testes diferenciais divergem.
- Modo debug (futuro): detectar overflow e abortar com `integer overflow` — no LLVM via
  `llvm.sadd.with.overflow`, no interpretador com checagem. `D-5` fica aberto até existir
  o codegen.
- `Float` é IEEE-754 binary64: `0.1 + 0.2 != 0.3`. Isso é esperado e documentado; **não**
  arredondar comparações. Para dinheiro, a resposta é `Decimal`/inteiro de centavos, não
  epsilon.
- Precisão exata de `Int` em `Float`: até 2^53. Acima disso, `Int as Float` pode perder
  bits — permitido, documentado.

### 3.6 Formatação (`D-6`)

`stringify` é contrato de testes (todo `// expect:` depende dele). Proposta:

| Valor | Saída |
| --- | --- |
| `Int 42` | `42` |
| `Float 42.0` | `42.0` (com `.0`, para distinguir de `Int`) — **muda o comportamento atual** |
| `Float 3.14` | `3.14` |
| `Float 1e20` | `1e+20` (notação científica a partir de certa magnitude) |
| `Float -0.0` | `-0.0` |
| `Float NaN` | `NaN` |
| `Float +inf` | `inf` / `-inf` |
| `Bool` | `true` / `false` |
| `Nil` | `nil` |

Duas abordagens para `Float`:
- **curta e round-trip** (Ryu/Grisu, como Rust/JS): `0.1+0.2` → `0.30000000000000004`;
- **limitada** (`%.15g`/`%.17g`): mais "bonita", mas pode não voltar ao mesmo valor.

Recomendação: **round-trip** (correção > estética) e nunca imprimir `1.0` como `1` quando
o tipo for `Float`, senão o teste não sabe se o valor é `Int` ou `Float`.

Impacto: `tests/cases/*` e `bench` hoje esperam `10` para `4 * 2.5`. Ao separar `Int` e
`Float`, esse caso passa a imprimir `10.0` e **os golden cases precisam ser atualizados
no mesmo commit** — é exatamente o tipo de mudança que o `TODO.md` §11 exige registrar.

### 3.7 `NaN`, infinito e zero negativo (`D-7`)

- Divisão por zero é erro (§3.4) → `inf` só aparece via `math.inf`/overflow de float.
- `NaN != NaN` (IEEE). Igualdade deve seguir IEEE; `is_nan(x)` explícito.
- Comparações com `NaN` são `false` (inclusive `<` e `>`); ordenar lista com `NaN` é
  comportamento indefinido — documentar.
- `-0.0 == 0.0` é `true`, mas `1 / -0.0` seria `-inf` (não acontece: divisão por zero é
  erro). `stringify(-0.0)` preserva o sinal.

### 3.8 Conversões e funções matemáticas (`D-8`)

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

### 3.9 Operadores bit a bit (`D-9`)

Só para `Int`, sem promoção (ainda **não implementado**):

```lox
a & b   // and
a | b   // or
a ^ b   // xor
~a      // not (complemento de 64 bits)
a << n  // shift left; n em [0, 63] senão erro (evita UB no LLVM)
a >> n  // shift aritmético (sinal); >>>
```

Precedência: `|` < `^` < `&` < shift, abaixo de comparação, acima de `+`? A convenção C
(`&` abaixo de `==`) é uma armadilha; adotar precedência **toda acima de comparação**
(como Rust) e registrar `D-9`.

### 3.10 Ranges (`D-10`)

```lox
0..10      // Range Int, fim exclusivo
0..=10     // Range Int, fim inclusivo
for i in 0..n { ... }
```

- Só `Int` no início (range de `Float` não tem passo natural) — `D-10`.
- `Range` é tipo próprio, iterável; `len(r)`, `contains`.
- `for i in 0..n` é o substituto do `for` C-style (§1.3 do TODO).
- Decidir se `..` cria lista (eager) ou é iterador preguiçoso: **iterador** (P2).

### 3.11 Inferência de tipos numéricos

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
puramente estática.

### 3.12 Mapeamento em LLVM (`D-11`)

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

### 3.13 Representação em runtime (`D-12`)

Ordem de evolução (detalhada no `TODO.md` §6.3):

1. **MVP**: valores boxeados `{ i8 tag, i64 payload }`; `Int` e `Float` com tags distintas.
2. **Otimização**: `Int`/`Float`/`Bool` desboxados quando o type checker conhece o tipo
   (monomorfização). `Any` permanece boxeado.
3. **Avançado**: NaN-boxing (payload em bits de `double`), reservando padrões para
   `nil`/`bool`/ponteiro; ~48 bits de ponteiro em x86-64.

Separar `Int` e `Float` desde o início evita que a representação mude quando a otimização
chegar.

### 3.14 Performance e benchmarks

Quando o modelo numérico entrar, adicionar benchmarks específicos:

- laço com `Int` puro (já existe: `loop_sum`);
- laço com `Float` (novo) — mede custo de conversão/promoção;
- `fib` recursivo (após o cap. 10) — mede chamadas, não números;
- comparação interpretador × LLVM no mesmo `.lox` (`TODO.md` §7).

`Int` em Python é um objeto; `Float` também. O ganho real de performance só vem com o
backend nativo — no interpretador, o objetivo é **correção**, não velocidade.

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

| Tipo | `==` | Hash | Ordenável |
| --- | --- | --- | --- |
| `Int`/`Float` | numérica com promoção (`1 == 1.0` → `true`) | por valor numérico normalizado | sim |
| `Nil` | só igual a `Nil` | constante | não |
| `Bool` | por valor; **nunca** igual a número | sim | `false < true`? evitar |
| `String` | conteúdo | conteúdo | sim (léxico) |
| `List` | elemento a elemento | combinação dos elementos | não |
| `Map` | igualdade estrutural? | inviável em geral | não |
| objeto | identidade (padrão) ou `__eq__` explícito | identidade | não |

Ponto delicado: `1 == 1.0`. Recomendação (`D-18`): **`true`** (igualdade numérica),
porque o usuário pensa em números, não em representações; mas `Int 1` e `Float 1.0` são
tipos diferentes para o checker. Documentar; hash de `1` e `1.0` deve ser igual se ambos
forem chave de `Map`, senão o mapa quebra.

---

## 11. Decisões em aberto

| Id | Decisão | Opções | Recomendação |
| --- | --- | --- | --- |
| `D-1` | modelo numérico | `Number` único / `Int`+`Float` / + `Decimal` | **`Int`+`Float`** |
| `D-2` | literais | separadores, bases, sufixos, `.5`/`1.` | bases + `_`; sem sufixos |
| `D-3` | promoção | só `Int→Float` / nenhuma / coercitiva | só `Int→Float` implícito |
| `D-4` | divisão/módulo | `/` float vs int; `%` truncado vs floored | `/`→Float, `//` int, `%` truncado |
| `D-5` | overflow | wrapping / checado / saturante | wrapping; debug checado |
| `D-6` | formatação | round-trip vs `%g`; `42.0` vs `42` | round-trip, `42.0` |
| `D-7` | NaN/Inf | IEEE completo / proibir | IEEE + erro em div/0 |
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
| `D-18` | `1 == 1.0` | `true` / `false` / erro | **`true`** |

Cada decisão precisa de: um caso golden demonstrando o comportamento, uma linha no
`TODO.md` §11 e (quando for semântica) atualização do `AGENTS.md` §3.

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

Ordem prática: N0–N1 cabem **antes** do cap. 10 e já valem teste; N2+ só depois do
resolver (cap. 11), porque o checker depende de escopo.

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
