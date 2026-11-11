# ADR-0013 — Ternário, `??`, `?.` e escapes de string

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TODO.md`](../../TODO.md) §1.3/§11,
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/semantica.md`](../spec/semantica.md),
  [`../spec/lexico.md`](../spec/lexico.md), [`../spec/erros.md`](../spec/erros.md)
- **Implementação:** `src/expr.py`, `src/parser.py`, `src/scanner.py`,
  `src/checker.py`, `src/interpreter.py`, `src/ast_printer.py`, `src/ty.py`;
  testes em `tests/cases/ternary.lox`, `tests/cases/nil_aware.lox`,
  `tests/test_scanner.py`, `tests/test_parser.py`, `tests/test_checker.py`

## Contexto

Faltavam expressões condicionais e formas de lidar com `nil` sem `if` manual. O `or` atual
é truthiness (Python): `0 or 5` → `5`, `false or true` → `true`; isso não serve para
“só nil”. Optional chaining e coalescência são operadores distintos — um evita o acesso a
`nil`, o outro troca o valor `nil` por um default. Strings também eram cruas: `"\n"` era
barra + `n`, o que atrapalha qualquer mensagem/format.

## Decisão

### 1. Ternário `a if cond else b`

- Sintaxe Python-style, parênteses **opcionais**:
  ```lox
  val status = "adulto" if idade >= 18 else "menor"
  ```
- Precedência: abaixo de `or` e de `??`, acima da atribuição; o `else` é associativo à
  direita:
  ```
  a if c else b if d else e   ==   a if c else (b if d else e)
  ```
- Condição segue a truthiness da linguagem (não exige `Bool`).
- Só o ramo escolhido é avaliado.
- Tipo: `union(then_type, else_type)`; `Int`/`Int` → `Int`, `Int`/`Float` →
  `Int | Float`, ramo `Nil` torna o resultado anulável.
- `if`/`else` continuam keywords; não há `? :`.
- Falta de `else` é erro de sintaxe (`Expect 'else' after conditional expression.`).

### 2. `??` — coalescência de nil

- `a ?? b` devolve `a` se `a != nil`, senão avalia `b`.
- Diferente de `or`: `false ?? true` → `false`; `0 ?? 5` → `0`; `"" ?? "x"` → `""`.
- Só o lado direito é avaliado quando o esquerdo é `nil`.
- Associativo à direita e com precedência **abaixo de `or`** e **acima do ternário**:
  `a ?? b or c` = `a ?? (b or c)`.
- Tipo: `non_nil(A) | B`; se `A` já é comprovadamente non-null, o tipo é `A` (o lado
  direito nunca roda).
- Não existe `?:` elvis; seria a mesma coisa com outra grafia.

### 3. `?.` — optional chaining

- Sintaxe `a?.b` e `a?.m()`.
- `nil?.x` → `nil`; `nil?.m()` → `nil` sem chamar o método.
- `a?.b.c` protege só `a`; se `b` for nil, `.c` ainda é erro. Para proteger cada passo,
  `a?.b?.c`.
- `a?.b = 1` é inválido (`Can't assign through optional chaining.`).
- Em chamada, o `?.` protege o **receptor** e os argumentos só são avaliados se o
  receptor não for nil. `a?.m()`:
  - `a` nil → nil, sem avaliar `m` nem argumentos;
  - `a` não nil → chama `m`; método ausente continua erro.
- Para proteger o resultado da chamada, use outro `?.` ou `??`:
  `a?.m()?.x`, `a?.m() ?? default`.
- Tipo:
  - objeto non-null `T` → tipo normal da propriedade/método;
  - objeto `T | Nil` → `P | Nil` (o `?.` acrescenta `Nil`);
  - `nil?.x` é `Nil`;
  - em `a?.m()`, o resultado é `ret | Nil` quando o receptor é anulável.
- `?.` não é default: `a?.b` pode continuar nil; `??` é que troca por default.

### 4. Escapes de string

Strings comuns processam:

| Escape | Resultado |
| --- | --- |
| `\n` | newline |
| `\t` | tab |
| `\r` | carriage return |
| `\"` | aspas |
| `\\` | barra invertida |
| `\0` | NUL (`\x00`) |
| `\u{XXXX}` | code point Unicode (`\u{1F600}`) |

- Escape desconhecido é erro léxico:
  `Unknown escape sequence '\q'.`
- `\u` exige `{...}` com 1–6 dígitos hexadecimais; valor fora de `0..10FFFF` ou surrogate
  (`D800..DFFF`) é `Invalid Unicode escape.`
- Strings continuam podendo conter newlines reais; `\u{...}` não substitui `"""..."""`.
- Não entram ainda: interpolação `"${expr}"`, triple-quoted e raw strings.

## Consequências

### Positivas

- Ternário legível sem token novo; expressão de verdade em `val`, `return`, argumentos.
- `??` separa claramente “nil” de “falsy”; `or` continua Python-like.
- `?.` evita a pirâmide de `if (x != nil)` e compõe com `??`.
- Escapes deixam strings utilizáveis em mensagens, caminhos e testes; `\u{}` cobre Unicode.
- Optional call curto-circuita argumentos, evitando efeitos colaterais inesperados.

### Negativas / custos

- Três formas novas de expressão e um flag extra em `Get`/`Call`; o visitor ganha
  `Conditional`.
- `?.` em união de classes exige todos os membros terem a propriedade com o mesmo tipo.
- `a?.b.c` e `a?.b?.c` diferem; é preciso documentar e testar.
- Escapes mudam o valor de strings existentes com `\n` literal; não havia testes
  dependendo disso, mas é uma mudança observável.
- `??` e `or` podem ser confundidos; a documentação precisa reforçar a diferença
  `0`/`false`/`""`.
- `??`/`?.` ainda não resolvem narrowing posterior (`if x != nil`), que continua T5.

### Neutras

- `Logical` reutiliza `??`; não há nó novo para coalescência.
- `Get`/`Call` ganham `optional: bool` com default `False`, preservando construções
  existentes.
- `\u{}` usa `chr`; não há normalização Unicode de identificadores.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `cond ? a : b` | `?`/`:` já são usados em tipos/anotações; menos legível |
| `if cond then a else b` | cria outra gramática de `if`, precisa de `then` e conflita com statement |
| `?:` elvis | duplicaria `??` com outra grafia |
| `or` como default | truthiness: `0`, `false`, `""` seriam trocados indevidamente |
| `?.` só em propriedade, sem chamada | `a?.m()` é o caso mais útil; deixaria buraco |
| `?.` como default | confunde “acesso seguro” com “valor padrão”; são operações distintas |
| Interpolação junto com escapes | scanner/parser/`toString` são outro pacote; fica para depois |
| Dedent automático em `"""` | ambiguidade de indentação; fica para uma decisão futura |

## Como verificar

- `tests/cases/ternary.lox` — valor, truthiness, aninhamento e curto-circuito;
- `tests/cases/nil_aware.lox` — `?.`, `??`, chamada opcional e combinação;
- `tests/cases/errors/ternary_missing_else.lox` e `optional_assignment.lox`;
- `tests/test_scanner.py` — escapes, `\u{}`, `??` e `?.`;
- `tests/test_parser.py` — precedência de ternário/`??`/`?.` e AST;
- `tests/test_checker.py` — tipos de união, `non_nil`, optional call;
- `make check` e `make bench`.

Critério para revisar: se `if` expression virar bloco/`match`, se `??` ganhar variante
`?:`, se optional chaining precisar de indexação (`a?.[i]`), ou se strings ganharem
interpolação/triple/raw.
