# ADR-0012 — Comentários, `//`, `**` e operadores de bits

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TIPOS.md`](../../TIPOS.md) (`D-4`, overflow),
  [`../spec/lexico.md`](../spec/lexico.md), [`../spec/sintaxe.md`](../spec/sintaxe.md),
  [`../spec/semantica.md`](../spec/semantica.md), [`../../TODO.md`](../../TODO.md) §1/§3
- **Implementação:** `src/frontend/scanner.py`, `src/frontend/token_type.py`, `src/frontend/parser.py`,
  `src/execution/numeric.py`, `src/execution/interpreter.py`, `src/semantics/checker.py`; testes em
  `tests/test_scanner.py`, `tests/test_parser.py`, `tests/test_checker.py` e
  `tests/cases/*.lox`

## Contexto

`//` era comentário de linha, mas queremos `//` como divisão inteira. Isso obriga a
repensar comentários. Ao mesmo tempo, a linguagem ganha potência (`**`) e operadores de
bits (`& | ^ ~ << >> >>>`), que precisam de semântica de 64 bits, tipos e precedência
explícitas. O `Int` já é i64 com wrapping (`ADR-0006`), e o checker já separa `Int` de
`Float`; a base é adequada.

## Decisão

### 1. Comentários

- `#` inicia comentário de linha até o fim da linha.
- `/* ... */` é comentário de bloco **aninhado** (`/* /* */ */` é válido); um bloco não
  fechado é erro léxico: `Unterminated block comment.`
- `//` deixa de ser comentário e vira operador.
- Consequência para o futuro literal de mapa: `#{}` fica impossível; usar `{}` ou
  `Map{}` quando `D-14` for decidido. `#` dentro de string não é comentário.
- Os marcadores dos golden cases passam de `// expect:` para `# expect:`.

### 2. `//` — divisão inteira

- `Int // Int -> Int`, **truncada em direção a zero**:
  `7 // 2 == 3`, `-7 // 2 == -3`, `7 // -2 == -3`, `-7 // -2 == 3`.
- Consistente com o `%` truncado atual: `a == (a // b) * b + (a % b)` para `b != 0`.
- Só `Int`; `Float`/`Bool`/mistura são erro de tipo. `/` continua sempre `Float`.
- Divisor zero é erro de runtime (`Division by zero not allowed`).
- Overflow de `INT_MIN // -1` faz **wrap i64** (`INT_MIN`), como `+`/`*`.
- Mesma precedência de `*`, `/` e `%`.

### 3. `**` — potência

- Associativo à direita: `2 ** 3 ** 2 == 2 ** (3 ** 2) == 512`.
- Precedência matemática: `-2 ** 2 == -(2 ** 2) == -4`; o lado direito aceita unário,
  então `2 ** -1` é parseado como `2 ** (-1)`.
- `Int ** Int -> Int`; expoente negativo é **erro de runtime**:
  `Negative exponent not allowed for integer power.`
  Para resultado fracionário use base `Float`: `2.0 ** -1 == 0.5`.
- Qualquer `Float` envolvido (`Float ** Int`, `Int ** Float`, `Float ** Float`) devolve
  `Float`; `Int` é promovido. `Int ** Float` é útil para raízes (`2 ** 0.5`).
- `0 ** 0 == 1`; `0.0 ** 0.0 == 1.0`.
- Overflow de `Int` faz wrap i64 (`2 ** 63 == INT_MIN`), com exponenciação rápida.
- Em `Float`: domínio inválido (`(-1.0) ** 0.5`, `0.0 ** -1.0`) é
  `Invalid exponentiation.`; overflow é `Exponentiation overflow.`
- Mesma precedência de unário do Python (acima da multiplicação; ver acima).

### 4. Operadores de bits

- Operadores: `&` (and), `|` (or), `^` (xor), `~` (not unário), `<<` (shift left),
  `>>` (shift right aritmético) e `>>>` (shift right lógico).
- **Só `Int`** (i64 two’s complement); `Bool` e `Float` são erro no checker e no runtime.
  `|` compartilha o token com uniões de tipo, mas os contextos são distintos.
- Resultado é sempre i64, com wrapping:
  - `~x == -x - 1`;
  - `&`, `|`, `^` operam nos 64 bits;
  - `<<` descarta os bits altos;
  - `>>` preenche com o bit de sinal (`-1 >> 1 == -1`);
  - `>>>` converte para o padrão unsigned de 64 bits, desloca e reinterpreta como i64
    (`-1 >>> 1 == INT_MAX`, `-1 >>> 63 == 1`).
- Contagem de shift precisa estar em `0..63`; fora disso:
  `Shift count must be between 0 and 63.` (erro de runtime, não máscara).
- Precedência (baixa → alta), escolhida para evitar a armadilha do C:

  ```
  or
  and
  == !=
  < <= > >=
  |          (bitwise)
  ^
  &
  ..         (range)
  << >> >>>
  + -
  * / // %
  unário not - ~
  **         (associativo à direita; lado direito aceita unário)
  chamada
  primary
  ```

  Assim `flags & MASK == 0` é `(flags & MASK) == 0`, e shifts continuam abaixo de
  `+`/`-` (`a + b << c == (a + b) << c`). `~` fica no nível unário.
- Erros de runtime: `Operands must be integers.` (binário) e
  `Operand must be an integer.` (`~`).

## Consequências

### Positivas

- `//` e `**` completam a aritmética com `Int`/`Float` separados.
- Bits têm semântica de 64 bits explícita, mapeável para `and`/`or`/`xor`/`shl`/`ashr`/
  `lshr` do LLVM; não há UB silencioso para shift.
- Comentários `#` + bloco aninhado são simples e liberam `//` sem ambiguidade com
  subtração (diferente de `--`).
- Precedência de bits evita o bug clássico `flags & MASK == 0`.

### Negativas / custos

- `2 ** -1` é erro; é preciso escrever `2.0 ** -1`. Quem quer sempre fracionário deve
  usar base `Float`.
- `#` impede `#{}` como literal de mapa; `D-14` precisa usar outra forma.
- Contagem de shift fora da faixa exige checagem no runtime/LLVM (branch/guard).
- `>>>` é mais um token e uma regra; quem não usa bits pode ignorar.
- Comentários de bloco com newlines contam linhas e podem afetar a regra de `;` opcional
  (um operador depois de um bloco multi-linha pode começar outra linha e não continuar a
  expressão); documentar e evitar quebrar expressão dentro de bloco multi-linha.
- O lexer fica maior: `//`, `**`, `<<`, `>>`, `>>>`, `&`, `^`, `~` e aninhamento de bloco.

### Neutras

- AST não muda: `Binary`/`Unary` reutilizam os tokens; `//` e `**` são operadores.
- `|` já existia para tipos; nenhum conflito de parser.
- Goldens e exemplos precisam migrar comentários para `#`.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter `//` comentário e usar `div` para divisão inteira | o pedido é `//`; `div` fica menos claro e foge da convenção |
| `--` para comentário | ambiguidade com `a--b`; exigiria regra contextual frágil |
| `#` só de linha, sem bloco | mais simples, mas perde comentários multilinha; o aninhamento é barato |
| `//` floor (Python) | inconsistente com `%` truncado; exigiria mudar `%` e quebrar testes |
| `Int ** Int -> Float` sempre | perderia `2 ** n` inteiro, útil para bits e loops |
| `Int ** Int -> Int \| Float` | tipo depende do valor; atrapalha aritmética e `--check` |
| `>>` lógico e `>>>` aritmético | contraintuitivo; Java/Kotlin usam `>>>` para lógico |
| Mascarar shift (`& 63`) | `1 << 64 == 1` esconde bug; erro é mais previsível |
| Precedência C para bits | `flags & MASK == 0` vira `flags & (MASK == 0)` |

## Como verificar

- `tests/test_scanner.py` — `#`, bloco aninhado, `//` como token, `**`, shifts;
- `tests/test_parser.py` — precedência de bits, `//`, `**` e unário;
- `tests/test_checker.py` — `//`/bits só `Int`, `**` `Int`/`Float`;
- golden cases: `comments.lox`, `int_division.lox`, `exponentiation.lox`,
  `bitwise.lox`, `bitwise_precedence.lox`, `shift_count.lox`;
- erros: divisor zero, expoente negativo, shift inválido, tipo errado, bloco não fechado;
- `make check` e `make bench`.

Critério para revisar: se houver unsigned (`UInt`/`u64`), se `>>`/`>>>` mudarem de
convenção, se `Int` deixar de ser two’s complement, ou se `#` colidir com um literal de
mapa.
