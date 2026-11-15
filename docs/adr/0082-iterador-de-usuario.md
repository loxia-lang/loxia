# ADR-0082 — Iterador de usuário no `for-in`

- **Status:** accepted (implementado: tree-walk, checker e backend)
- **Data:** 2026-11-15
- **Relaciona:** [ADR-0007](0007-ranges-e-iteracao.md) (protocolo embutido),
  [ADR-0040](0040-generics-classes-desenho.md) (classes genéricas),
  [ADR-0080](0080-interfaces-nominais-implementacao.md) (interfaces)

## Contexto

O `for x in` conhece um conjunto fechado de fontes: `Range`, `String`, `List`, `Map` e
tupla. O [ADR-0007](0007-ranges-e-iteracao.md) adiou iteráveis de usuário porque o
protocolo precisava de uma sentinela de fim (`T?`) e de traits. As duas coisas já existem:
`T?` desde o ADR-0018 e interfaces nominais desde o ADR-0080. Sem isso, uma classe que
representa uma sequência (árvore, stream, página, gerador) não entra no `for-in` e precisa
expor `List` materializada ou um `while` manual.

## Decisão

### 1. Protocolo estrutural `iter()`/`next()`

```lox
class ContadorIter {
  fn next() -> Int? { ... }   # nil encerra; outro valor é o elemento
}

class Contador {
  fn iter() -> ContadorIter { return ContadorIter(...); }
}

for x in Contador(3) { print x; }
```

- `for x in e` chama **`e.iter()` uma vez**; o resultado precisa ser um objeto com
  `next() -> T?`.
- `next()` é chamado a cada iteração; `nil` encerra; qualquer outro valor vira o `x`.
- O protocolo é **estrutural**: a classe não precisa declarar `implements`. A interface
  nominal continua disponível para tipar o iterador (`iter() -> IntIter`, com
  `next() -> Int?` na interface), mas o `for-in` não exige um nome de interface.
- O iterador pode ser a própria instância (`fn iter() -> C { return this; }`) ou um objeto
  novo; `iter()` é chamado a cada `for`, então dois `for` aninhados sobre a mesma fonte
  recebem iteradores independentes se a implementação devolver um novo.
- `T` não pode ser `Any` nem `Nil`: `next() -> Any?`/`next() -> Nil` são recusados no
  `--check` (o backend precisa de uma representação concreta para o elemento).
- `iter()`/`next()` precisam ter **zero parâmetros**. `next()` pode ter defaults, mas
  `len(params) == 0` é exigido na v1; o runtime chama sem argumentos.

### 2. Checker

Para `ClassTy` e `InterfaceTy`:

1. resolve `iter` (próprio, herdado ou default de interface);
2. exige `iter() -> I` com `I` classe/interface;
3. resolve `next` em `I`;
4. exige `next() -> T?`, com `T` concreto;
5. o tipo do laço é `T` (o `non_nil` do retorno).

Classes genéricas são suportadas: `iter() -> BoxIter[T]` e `next() -> T?` são
substituídos pelos argumentos da instanciação. `Any` continua produzindo elemento `Any`
(o runtime decide), como nas outras fontes.

Erros dirigidos (todos `INVALID_ITERATION`):
`'C' is not iterable: define iter() returning an iterator with next() -> T?.`,
`iter() must take no arguments.`, `iter() must return an iterator with next() -> T?.`,
`next() must take no arguments.`, `next() must return T?`, e
`next() must return T? with a concrete T.`.

> Ordem de declaração: como em qualquer classe usada no corpo de outra, a classe do
> iterador precisa aparecer **antes** da classe que a constrói quando o `init` dela é
> chamado no corpo de `iter()`. O checker pré-declara nomes de classe, não as assinaturas
> de métodos de todas as classes.

### 3. Runtime (tree-walk)

`_iterate` reconhece `LoxInstance`:

- chama `iter()` via `LoxInstance.get(...).call(interpreter, [])`;
- exige que o resultado seja `LoxInstance`;
- em loop, chama `next()` e para no primeiro `nil`; valores não-nil são produzidos.

O `for-in` continua criando um `Environment` novo por iteração e a variável do laço
continua `val` (ADR-0007). Mutar a fonte durante a iteração é responsabilidade do
protocolo; não há snapshot nem contador de modificação.

### 4. Backend LLVM

- `_for_in` ganha o caminho `INSTANCE`: chama `iter()` uma vez, obtém a descrição do
  retorno de `next()` pelo layout do iterador (classe, default de interface ou interface
  pura), chama `next()` no header e usa a tag de `T?` para escolher corpo/fim.
- O elemento é o payload do opcional; o laço reusa o mesmo `_for_bind` das fontes
  embutidas (inclusive captura por célula).
- Classes genéricas usadas **dentro** de outra classe genérica (`BoxIter[T]` dentro de
  `Box[T]`) passam a ser emitidas sob demanda: o backend materializa o descritor da
  instanciação no ponto da chamada, uma vez, em vez de depender de uma instanciação
  concreta vista no topo do programa.
- Não há ABI nova: `iter()`/`next()` são métodos normais; o opcional usa a representação
  do ADR-0047.

## Consequências

- Qualquer classe com `iter()`/`next() -> T?` entra no `for-in`, com tipo de elemento
  inferido e sem materializar lista.
- O protocolo é aberto (estrutural) e não aumenta o orçamento sintático: nenhuma palavra
  nova, nenhuma forma de declaração nova.
- `next()` é stateful; a fonte precisa devolver um iterador novo em `iter()` para ser
  reutilizável/nested. Isso é contrato do usuário, não do `for`.
- `nil` é sentinela: um iterador não pode produzir `nil` como elemento. Para isso seria
  preciso um `Option` próprio (`Result`/enum), fora da v1.
- O checker não faz análise de fluxo do iterador (finito, sem mutação); um `next()` que
  sempre devolve valor gera laço infinito, como um `while` do usuário.

## Alternativas

| Alternativa | Por que não |
| --- | --- |
| Exigir `implements Iterable`/`Iterator` | Interfaces não são genéricas; o elemento viraria `Any` e a stdlib não ganharia tipo |
| `for` sobre objeto com `next()` direto | não separa fonte de estado; dois `for` na mesma fonte quebrariam |
| `iter()` devolvendo `List` | materializa e exclui streams/árvores; o protocolo `next()` já cobre |
| `Option`/enum como sentinela | mais um tipo e cerimônia para o caso comum; `nil` já é o “sem valor” da linguagem |
| `Iterator[T]` genérico embutido | exigiria interface genérica, reificação e mais ABI; fica para depois |

## Como Verificar

- `tests/cases/user_iterator.lx` (l6): `Int`, `String`, interface `IntIter`, iterador
  genérico `BoxIter[T]`, fonte genérica `Box[T]`, `for` aninhado e `RangeBox`; roda no
  tree-walk e no backend.
- `tests/test_checker.py::test_iterator_errors` cobre oito erros (sem `iter`, aridade,
  retorno não-iterador, sem `next`, aridade, não-opcional, `Any?`, `Nil`).
- `tests/test_backend.py` cobre o caso no diferencial; o teste de ABI não muda.
- `make check` verde; `make bench` sem regressão (o caminho quente de `for-in` embutido
  não mudou).
