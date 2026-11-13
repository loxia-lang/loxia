# ADR-0025 — `is T` e narrowing de uniões

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0018](0018-narrowing.md), [ADR-0023](0023-soundness-do-checker.md),
  [ADR-0024](0024-mutacao-monomorfica.md),
  [`../../TODO.md`](../../TODO.md) §2, [`../../TIPOS.md`](../../TIPOS.md) §5,
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/frontend/expr.py`](../../src/frontend/expr.py), [`src/frontend/parser.py`](../../src/frontend/parser.py),
  [`src/execution/interpreter.py`](../../src/execution/interpreter.py), [`src/execution/type_test.py`](../../src/execution/type_test.py),
  [`src/semantics/checker.py`](../../src/semantics/checker.py), [`src/frontend/ast_printer.py`](../../src/frontend/ast_printer.py),
  [`tests/test_checker.py`](../../tests/test_checker.py),
  [`tests/test_interpreter.py`](../../tests/test_interpreter.py)

## Contexto

Uniões já existiam (`Int | String`, `Animal | Nil`), mas só `nil`/truthiness estreitavam.
Sem `is`, uma união não-nil era praticamente inutilizável:

```lox
fn describe(x: Int | String) -> String {
  if (x is Int) { return "int" }   # não existia
  return x
}
```

O runtime tem tipos apagados; o teste precisa existir só para `is` e narrowing, sem
transformar o tree-walk em um sistema de tipos dinâmico.

## Decisão

### Sintaxe e runtime

`expr is Tipo` é uma expressão que devolve `Bool`. O lado direito usa a gramática de tipos
existente (`Int`, `Animal`, `List[Int]`, `Int?`, `A | B`), e `is` fica no nível de
comparação:

```lox
print 1 is Int;                 # true
print 1 is Float;               # false
print "a" is String;            # true
print nil is Nil;               # true
print [1, 2] is List[Int];      # true
print {"a": 1} is Map[String, Int];  # true
```

`matches_type(value, Ty)` em `src/execution/type_test.py` é a única ponte runtime:

- primitivos: `Nil`, `Bool`, `Int`, `Float`, `String`, `Range`;
- **classe**: qualquer instância da classe ou de uma subclasse;
- `List[T]`/`Map[K, V]`: confere os elementos/chaves/valores recursivamente (lista vazia
  satisfaz qualquer `T`);
- união: qualquer membro;
- `Any`: sempre verdadeiro; `Never`: sempre falso;
- **tipos de função** são recusados pelo checker (`is doesn't support this type yet.`).

Uma classe **como valor** (`Animal` sozinho) não é instância: `Animal is Animal` é
`false`. `x is Animal` testa instâncias.

### Narrowing

O checker refina **variáveis** em `if`/`elif`/`else`, `while` e condições com `and`/`or`:

```lox
fn f(x: Int | String) -> String {
  if (x is Int) { return "int" }
  return x                      # x: String no resto
}
```

- `x is T` verdadeiro refina para a **interseção** entre o tipo atual e `T`;
- falso remove da união os membros **totalmente cobertos** por `T`;
- `and` no ramo verdadeiro combina as interseções; `or` no ramo falso combina os restos;
- `while` aplica o refinamento verdadeiro ao corpo (o laço pode executar);
- `!`, agrupamento e `x != nil` continuam funcionando juntos.

Refinamentos são **de fluxo e de variável**: não cobrem `obj.campo`, `xs[i]`, merge de CFG
completo nem mutação de coleção após o teste. Atribuir à variável invalida o refinamento,
como já acontecia.

## Consequências

### Positivas

- Uniões não-nil passam a ser usáveis: `Int | String`, `Animal | Filhote`, `T | Nil`.
- O teste é explícito e determinístico; não há coerção.
- `List[T]`/`Map[K, V]` são testados de verdade (O(n)), não só a “casca”.
- `is` compõe com `and`/`or`, `while` e early return.
- O runtime continua apagado; a checagem estática fica no checker.

### Negativas / custos

- `is List[T]`/`Map[K, V]` percorre a coleção; em listas grandes, é O(n).
- Testar uma coleção mutável e depois mutá-la pode invalidar o refinamento; o checker não
  rastreia aliasing/mutação de coleção.
- Refinamento não cobre merge completo de fluxo; campos/índices literais entraram no
  [ADR-0032](0032-narrowing-campos-indices.md); `is` em expressão
  que não é variável devolve `Bool`, mas não estreita.
- Classes como valor não são instâncias; não há `is Class` na v1.
- Tipos de função não são suportados em `is` (nem assinatura nem aridade).
- A promoção `Int → Float` e a erasure fazem alguns testes serem mais “otimistas” do que o
  runtime (`Float` anotado pode conter `Int`); é a limitação conhecida.
- Um teste impossível (`x: String; if (x is Int)`) não é detectado como sempre falso; o
  corpo ainda é checado.

## Alternativas consideradas

| Alternativa | Por que não agora |
| --- | --- |
| Só `match`/pattern matching | `match` é P3 e maior; `is` resolve uniões agora |
| Método `x.is(Int)` | Tipo como valor de primeira classe não existe; keyword é mais clara |
| `is` só para classes | Deixaria `Int \| String` inutilizável; primitivos são baratos |
| Checar `List[T]` só pela casca | Seria uma mentira: `[1, "a"] is List[Int]` daria `true` |
| Refinar campos/índices agora | Precisa de aliasing/flow-sensitive; fica para depois |
| Tipos de função em `is` | Assinatura não é observável no runtime sem metadados; recusar é honesto |

## Como verificar

- `tests/test_scanner.py` (keyword `is`);
- `tests/test_parser.py` (`is` como expressão e precedência);
- `tests/test_ast_printer.py` (`(is x Int)`);
- `tests/test_interpreter.py` (`is` em primitivos, listas, mapas, classes, subclasses);
- `tests/test_checker.py`:
  - `test_is_narrows_union_and_else`;
  - `test_is_narrows_until_early_return`;
  - `test_is_narrows_class_to_subclass`;
  - `test_is_narrows_any_to_list`;
  - `test_is_rejects_function_types`;
  - `test_is_result_is_bool`;
  - `test_narrowing_in_and_and_while`;
- `make check` verde.

Critério para revisar: quando `match`/exhaustividade entrar, quando houver refinamento de
campos/índices ou quando tipos de função ganharem metadados de runtime.
