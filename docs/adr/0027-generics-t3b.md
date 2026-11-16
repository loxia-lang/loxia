# ADR-0027 — Generics T3b: funções, monomorfização e inferência

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0020](0020-assinaturas-explicitas.md), [ADR-0021](0021-tipos-de-funcao.md),
  [ADR-0026](0026-freeze-1.0.md), [`../../TODO.md`](../../TODO.md) §2,
  [`../../TIPOS.md`](../../TIPOS.md) §2.1, [`../spec/sintaxe.md`](../spec/sintaxe.md),
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`loxia_core/frontend/ty.py`](../../loxia_core/frontend/ty.py), [`loxia_core/frontend/stmt.py`](../../loxia_core/frontend/stmt.py),
  [`loxia_core/frontend/parser.py`](../../loxia_core/frontend/parser.py), [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py),
  [`loxia_core/frontend/ast_printer.py`](../../loxia_core/frontend/ast_printer.py),
  [`tests/test_checker.py`](../../tests/test_checker.py),
  [`tests/test_parser.py`](../../tests/test_parser.py),
  [`tests/test_interpreter.py`](../../tests/test_interpreter.py)

## Contexto

O freeze da 1.0 ([ADR-0026](0026-freeze-1.0.md)) deixou generics como a única trilha em
aberto. Sem generics, `map`/`filter`/`first` só existem para um tipo concreto; a biblioteca
não cresce.

A decisão precisava cobrir quatro eixos:

1. **codegen**: monomorfização, erasure/boxing ou híbrido;
2. **corpo genérico**: sem constraints, por instanciação ou com traits;
3. **escopo**: funções, classes ou métodos;
4. **chamada**: inferência ou type application explícita.

A escolha de codegen não muda o comportamento do tree-walk (tipos são apagados), mas muda
o ABI do LLVM. Foi feita antes do backend de propósito.

## Decisão

### 1. Monomorfização, não erasure/híbrido

O backend LLVM gera uma versão especializada por instanciação concreta:

```text
id(1)      -> id$Int
id("a")    -> id$String
map([1], f)-> map$Int$Int
```

- `Int` continua **unboxed** (i64), sem alocação.
- O código cresce com o número de instanciações; aceitável no MVP single-file.
- `Any` continua fora do backend L0–L2; monomorfização não exige representação dinâmica.
- O tree-walk **não** monomorfiza: `T` é apagado e `id(1)` só devolve `1`; o comportamento
  observável é o mesmo.

**Por que não híbrido agora?** Híbrido exige uma representação uniforme/boxed e dois
caminhos (especializado + dinâmico) antes de existir um caso de uso (módulos, `Any`,
existenciais, traits). Mono é menor para o MVP. Migrar mono → híbrido depois é **aditivo**:
as instanciações e a substituição de tipos já existem; adiciona-se um caminho boxed para
`Any`/dinâmico sem reescrever o checker. O custo de carregar híbrido agora é maior.

### 2. Corpo checado uma vez, sem constraints

O corpo é checado **uma vez** com `T` abstrato. Só valem operações universais:

- atribuir, passar, devolver, comparar `==`, usar `str`/`repr`;
- guardar/retirar de `List[T]`/`Map[String, T]`, iterar, indexar;
- chamar funções passadas como parâmetro (`fn(T) -> U`).

Não valem `a + b`, `len(x)` ou métodos de classe em `T` — nem todo `T` os tem:

```lox
fn soma[T] (a: T, b: T) -> T {
  return a + b;        # erro: Operands must be numbers.
}
```

Aritmética genérica exige traits/constraints (`T: Add`), que ficam para depois. A
alternativa “checar por instanciação” (template C++) foi recusada: erros dependem das
chamadas, função não chamada não é checada e o checker fica maior.

### 3. Só funções

```lox
fn id[T] (x: T) -> T { return x; }

fn map[T, U] (xs: List[T], f: fn(T) -> U) -> List[U] {
  val out: List[U] = [];
  for x in xs { out.push(f(x)); }
  return out;
}

print id(1);                              # 1
print map([1, 2], fn(x) => x * 2);        # [2, 4]
```

- `class Box[T]` e métodos genéricos **não** entram agora; `List`/`Map` já são genéricos
  embutidos. O resto fica em [`IDEIAS.md`](../../IDEIAS.md)/TODO.
- Um método declarado com `[T]` reporta `Generic methods aren't supported yet.`

### 4. Inferência apenas

Não existe `id[Int] (1)` na v1. O checker infere os tipos por unificação dos argumentos e do
tipo esperado:

```lox
fn empty[T] () -> List[T] { return []; }

val xs: List[Int] = empty();   # T = Int pelo contexto
print empty();                 # erro: Can't infer type argument(s) 'T'.
```

- Zero-arg genérico exige contexto (anotação, argumento de função, retorno).
- A inferência é da **esquerda para a direita**. Uma lambda que aparece antes do argumento
  que determina `T` (ex.: `apply(fn(x) => x * 2, 3)`) precisa anotar `x: Int`; os
  argumentos que fixam `T` devem vir antes.
- A forma explícita `id[Int] (1)` é ambígua com indexação (`xs[0]`) e fica para depois; hoje
  reporta `Type arguments on a call aren't supported; let the checker infer them.`
- Funções genéricas **não são valores de primeira classe** na v1: `val f = id` é erro;
  chame `id(...)`. Passar `id` como callback também é erro; use uma lambda.

### 5. Recursão e limites

- Recursão com os **mesmos** argumentos de tipo é permitida:
  ```lox
  fn length[T] (xs: List[T]) -> Int {
    if (len(xs) == 0) { return 0; }
    return 1 + length(xs);
  }
  ```
- Recursão que muda os argumentos de tipo é recusada:
  ```lox
  fn grow[T] (x: T) -> Int { return grow([x]); }
  # Polymorphic recursion is not supported yet; the type arguments must stay the same.
  ```
- Recursão mútua com crescimento de tipos não é detectada na v1; o backend terá um limite
  de instanciação. Documentado como limitação.

### 6. Freeze

Este ADR é a **exceção explícita** ao [ADR-0026](0026-freeze-1.0.md): T3b entra na 1.0,
limitado a funções, sem constraints, com inferência e monomorfização. Classes genéricas,
métodos genéricos, type application explícita, traits e funções genéricas como valor
continuam fora.

## Consequências

### Positivas

- `id`, `map`, `filter`, `first` e contêineres genéricos funcionam.
- Nenhuma representação boxeada no backend MVP; `Int` continua nativo.
- Erros de tipo aparecem na definição, não na chamada.
- O tree-walk não muda; a decisão de codegen fica registrada.
- A migração futura para híbrido é aditiva.

### Negativas / custos

- Sem `a + b`/`len(x)` em `T` até existir trait.
- Sem `class Box[T]`, métodos genéricos ou type application explícita.
- Função genérica não pode ser passada como valor; só chamada.
- Monomorfização gera código por instanciação (code bloat) e exige coletar instanciações no
  backend.
- Recursão polimórfica recusada; recursão mútua com tipos crescentes pode escapar da
  checagem e precisará de limite no codegen.
- `Map[T, V]` (chave genérica) é recusado sem constraint de chave.

## Alternativas consideradas

| Alternativa | Por que não agora |
| --- | --- |
| Erasure/boxing | Exige ABI uniforme e box de `Int`; mais lento e maior no MVP |
| Híbrido agora | Dois caminhos antes de haver `Any`/módulos/existenciais |
| Checar por instanciação | Erros tardios, corpo não checado, checker maior |
| Constraints/traits agora | Outra feature grande; conflita com o freeze |
| Classes/métodos genéricos | Layout/substituição de classe e codegen especializado; próximo passo |
| `id[Int] (1)` explícito | Ambiguidade com indexação; inferência cobre o caso comum |
| Função genérica como valor | Precisa de type application/contexto e codegen de função polimórfica |

## Como verificar

- `tests/test_parser.py::test_parses_generic_function_type_params`;
- `tests/test_ast_printer.py::test_dump_generic_function`;
- `tests/test_checker.py::test_generic_functions_identity_map_filter_and_context`;
- `tests/test_checker.py::test_generic_errors`;
- `tests/test_checker.py::test_generic_function_can_recurse_with_same_type_arguments`;
- `tests/test_interpreter.py::test_generic_types_are_erased_at_runtime`;
- `tests/cases/generics.lox`;
- `make check` verde.

Critério para revisar: traits/constraints, classes genéricas, type application explícita,
funções genéricas como valor, ou necessidade real de erasure/híbrido no backend.
