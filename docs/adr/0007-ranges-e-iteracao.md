# ADR-0007 — Ranges e iteração com protocolo embutido

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TIPOS.md`](../../TIPOS.md) `D-10`, [`../decisoes.md`](../decisoes.md), [`../../TODO.md`](../../TODO.md)
  §1/§11, [`../../IDEIAS.md`](../../IDEIAS.md) I-6,
  [`../spec/semantica.md`](../spec/semantica.md), [`../spec/sintaxe.md`](../spec/sintaxe.md)
- **Implementação:** `src/frontend/scanner.py`, `src/frontend/token_type.py`, `src/frontend/keywords.py`,
  `src/frontend/expr.py`, `src/frontend/stmt.py`, `src/frontend/parser.py`, `src/semantics/resolver.py`,
  `src/execution/interpreter.py`, `src/execution/lox_range.py`, `src/execution/natives/range.py`; casos em
  `tests/cases/for_in*.lox`, `range_value.lox` e `tests/cases/errors/for_in*.lox`,
  `range_*.lox`

## Contexto

Até aqui `for` é o C-style do livro. O plano de sintaxe pede `for x in iterável` e ranges;
List/Map ainda não existem, mas Range e String já são valores. Em Python, `range()` é uma
função que devolve um objeto lazy e `str` é iterável porque tudo implementa o protocolo de
iteração — um modelo que não queremos copiar inteiro (nem classes para primitivos, nem o
par iterável/iterador exposto). A discussão completa está em
[`IDEIAS.md` I-6](../../IDEIAS.md).

A pergunta central: **o que pode aparecer no `for x in` e como isso escala para tipos
futuros sem exigir OO?**

## Decisão

1. **Iteração é capacidade embutida, não hereditariedade.** Na v1, `for` conhece um
   conjunto fechado de fontes: `Range` e `String` (List/Map quando existirem). Classes de
   usuário entram depois via trait estrutural `Iterable[T]`; o iterator precisará de
   `next() -> T?`, o que depende de `Option` — por isso não expomos `iter()`/`next()`
   agora.

2. **Range é literal e valor lazy:** `a..b` é half-open (`a` incluso, `b` exclusivo),
   aceita apenas `Int`, avalia os bounds uma vez (esquerda→direita) e não materializa
   elementos (`0..1_000_000_000` é O(1)). Range é **reutilizável**: cada `for` cria a sua
   iteração; não é um iterator de uso único.

3. **Passo explícito vem da nativa `range(a, b, step)`**, com aridade fixa 3 (não há
   defaults ainda). Passo 0 é erro de runtime; `a..b` equivale a `range(a, b, 1)`.
   `..=` (inclusivo) fica **adiado** até existir um caso real.

4. **O que cada fonte produz:** `Range` → `Int`; `String` → `String` de 1 code point
   (consistente com `len` em code points, `D-13`); `List[T]` → `T` em ordem; `Map[K, V]` →
   chaves em **ordem de inserção** (determinismo do I-4; pares virão com `Tuple`).

5. **A variável do laço é um `val` novo por iteração.** Reatribuí-la é erro de compilação,
   e closures capturam o valor daquela iteração (evita o *late binding* do Python).

6. **Mutar a coleção durante a iteração é proibido/indefinido na v1** — documentado em vez
   de snapshot (custo de memória) ou contador de modificação (custo por escrita).

7. **Stdlib:** `map`/`filter`/`zip` devolverão `List` **eager** quando existirem; Range
   continua lazy; `contains` será função livre, não operador `in` (o `in` é só do for-in).

8. **Range é valor de primeira classe:** `print 0..3` mostra `<range 0..3>`, igualdade é
   estrutural e Range é truthy como qualquer valor que não seja `nil`/`false`.

## Consequências

### Positivas

- `for x in` funciona sem List e sem OO, e o protocolo documentado não fecha a porta para
  classes de usuário.
- Range lazy evita alocar e casa com o codegen (laço aritmético).
- Half-open elimina o `len - 1` e o erro de off-by-one; range vazio não é erro.
- Variável imutável por iteração elimina uma classe de bug de closure.
- Ordem de inserção em Map preserva a reprodutibilidade exigida por I-4.

### Negativas / custos

- Sem `..=` não há range inclusivo; o usuário escreve `a..b + 1` (cuidado com overflow no
  futuro codegen).
- `range` de 3 argumentos é menos ergonômico que o do Python; `range(10)` só quando
  defaults entrarem ([ADR-0009](0009-defaults-e-campos.md), P3).
- `map`/`filter` eager podem alocar; um `Iter` lazy fica para depois, se houver dor.
- Iteráveis de usuário e o par `iter()`/`next()` não existem; classes não entram em
  `for-in` ainda.
- Mutação durante iteração depende de disciplina do usuário até haver checagem.

### Neutras

- Novos tokens `..` e a keyword `in` (18 palavras-chave).
- Nó `ForIn` na AST (não desaçucarado para `while`, para diagnóstico/codegen) e o nível de
  precedência `range` entre comparação e termo.
- `NativeError` interno para nativas reportarem erro no token da chamada.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só `range(...)` função, sem `..` | aridade variável/defaults ainda não existem; perde sintaxe e futuro pattern de match |
| Só `..`, sem `range(a,b,step)` | sem passo/descendente sem inventar segundo operador |
| Range eager (List) | `0..1_000_000_000` alocaria; perde o caso de uso principal |
| `for-in` desaçucarado para C-style no parser | perde diagnóstico “não iterável” e o codegen precisa do nó |
| `..=` já agora | superfície sem caso de uso; pode entrar depois |
| Iterável exigindo classe/interface desde já | precisaria de `Option`/traits e exporia `next()` cedo demais |
| `for` sobre instância com método `iter()` (duck typing) | sem sentinela de fim (Option) vira protocolo torto |
| `in` como operador de pertinência | mais um uso para a palavra; `contains` tipa e compila melhor |

## Como verificar

- `tests/cases/for_in.lox` (Range crescente/decrescente/vazio, String, aninhado);
- `tests/cases/for_in_capture.lox` (closure guarda o valor da iteração);
- `tests/cases/range_value.lox` (stringify, igualdade estrutural);
- `tests/cases/errors/for_in_immutable.lox`, `for_in_not_iterable.lox`,
  `range_bounds.lox`, `range_step_zero.lox`, `range_args_type.lox`, `range_arity.lox`;
- `tests/test_scanner.py` (token `..`, keyword `in`), `tests/test_parser.py` (`ForIn`,
  precedência), `tests/test_interpreter.py` (laço, captura, Range como valor);
- `make check`.

Critério para revisar: quando List/Map chegarem (fonte de iteração), quando `Option`
permitir o protocolo `Iterable` de usuário, ou se `..=`/passo virarem necessidade real.
