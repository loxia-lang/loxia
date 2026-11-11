# ADR-0006 — `Int` e `Float` separados (i64 + f64)

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TIPOS.md`](../../TIPOS.md) §3/§11 (`D-1`…`D-6`, `D-18`),
  [`../../TODO.md`](../../TODO.md) §11, [`../spec/lexico.md`](../spec/lexico.md),
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `src/scanner.py`, `src/numeric.py`, `src/values.py`,
  `src/interpreter.py`, `src/token_type.py`, `src/parser.py`; casos em
  `tests/cases/numbers.lox` e `tests/cases/errors/`

## Contexto

O Lox do livro tem **um** tipo numérico: `float` (IEEE-754 double). Todo literal `42` vira
`42.0`, e `stringify` esconde isso imprimindo `42`. Isso funciona para o interpretador,
mas cobra caro no caminho planejado: índices de lista, contadores e bitwise querem
inteiros exatos; no LLVM, `i64` e `double` são registradores e instruções diferentes, e
`Number` único força boxing ou conversões em todo lugar. O modelo completo está em
[`TIPOS.md`](../../TIPOS.md) §3; a decisão central é `D-1`.

## Decisão

1. **Dois tipos numéricos**: `Int` é `i64` com sinal; `Float` é IEEE-754 binary64 (f64).
2. **Literal decide o tipo**: sem `.` e sem expoente → `Int`; com `.` ou expoente →
   `Float` (`1` é `Int`, `1.0` e `1e9` são `Float`).
3. **Literais** (`D-2`): `_` como separador entre dígitos; bases `0x`, `0b`, `0o`; sem
   sufixos; `.5` e `1.` não são números; magnitude máxima é `2^63 - 1` (literal maior é
   erro de compilação; `INT_MIN` se obtém por aritmética, ex. `-9223372036854775807 - 1`).
4. **Promoção** (`D-3`): `Int op Float` promove para `Float`; `Float → Int` nunca é
   implícito. `1 + 2.0` é `3.0`, `1 / 2` é `0.5`.
5. **Divisão e resto** (`D-4`): `/` devolve **sempre `Float`** (`4 / 2` → `2.0`); `%` é
   resto truncado com sinal do dividendo (`-7 % 3` → `-1`), `fmod` quando há `Float`.
   Divisão/resto por zero é erro de runtime. A divisão inteira `//` **fica adiada**: o
   token colide com o comentário `//` e merece decisão própria (alternativas: `div`,
   `\`, ou trocar o comentário).
6. **Overflow** (`D-5`): aritmética `Int` faz *wrapping* de 64 bits; o interpretador
   simula o mesmo comportamento do `add`/`mul` do LLVM, para servir de oráculo.
7. **Formatação** (`D-6`): `Int` sai em decimal (`42`); `Float` sai na menor representação
   que faz round-trip e **sempre distingue** (`42.0`, `-0.0`, `0.30000000000000004`,
   `1e+20`, `NaN`, `inf`, `-inf`).
8. **Igualdade e comparação** (`D-18`): igualdade numérica com promoção (`1 == 1.0` →
   `true`); `Bool` nunca é número; `NaN != NaN` e comparações com `NaN` são `false`.

Fora do escopo deste ADR: bitwise (`D-9`), `as`/conversões (`D-8`), type checker e codegen.

## Consequências

### Positivas

- `Int` exato para índices/contadores e caminho nativo `i64` sem boxing.
- `stringify` deixa de esconder o tipo: `42` e `42.0` são distinguíveis.
- Regras de promoção explícitas e testadas agora, antes de a stdlib congelar a ordem dos
  argumentos e antes do checker.
- O interpretador simula o wrapping do LLVM, então os testes diferenciais futuros partem
  de um oráculo correto.

### Negativas / custos

- **Muda semântica do livro**: `/` agora é `Float` (`4 / 2` → `2.0`) e `4 * 2.5` imprime
  `10.0`; golden cases que imprimiam `10` foram atualizados no mesmo commit.
- Sem `//`, não há divisão inteira na linguagem até a decisão de token; quem precisa
  pode usar `(a / b) as Int` quando `as` existir.
- Literais negativos grandes não são representáveis diretamente (`-9223372036854775808`);
  a documentação indica a expressão equivalente.
- `Int` e `Float` são subtipos numéricos na cabeça do usuário, mas tipos distintos no
  checker futuro; a relação `Int <: Float` precisa ser respeitada (não vale para `List`).

### Neutras

- `%` ganhou token e nível de precedência (junto de `*` e `/`).
- `src/numeric.py` centraliza promoção, wrapping e comparação; o interpretador só decide
  mensagens de erro.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter `Number` único (double) | simples, porém perde exatidão > 2^53 e força boxing/conversão no LLVM |
| `Int` + `Float` + `Decimal` | dinheiro correto, mas escopo e runtime muito maiores agora |
| Implementar `//` trocando comentário para `#` | quebra todo o código existente e diverge do livro |
| `//` como divisão e `// ` (com espaço) como comentário | regra frágil e cheia de surpresa |
| Promoção também `Float → Int` (truncando) | bug silencioso clássico; conversão deve ser explícita (`as Int`) |
| `stringify` de `Float` com `%g`/estilo antigo | pode não fazer round-trip e esconde a diferença de tipo |

## Como verificar

- `tests/cases/numbers.lox` — literais (bases/`_`/expoente), promoção, `/`, `%`, igualdade,
  `-0.0` e wrapping;
- `tests/cases/errors/int_overflow.lox`, `invalid_number.lox`, `modulo_by_zero.lox`,
  `modulo_type.lox`, `division_float_by_zero.lox`;
- `tests/test_scanner.py` (literal `Int` vs `Float`, overflow, separador inválido),
  `tests/test_interpreter.py` (promoção, `/`, `%`, igualdade, wrapping, formatação);
- `make check` (ruff + mypy strict + pytest).

Critério para revisar: quando `//` ganhar token, quando o type checker impuser as regras
(`as`, aridade de promoção) ou se `Decimal` entrar no escopo — aí este ADR é substituído.
