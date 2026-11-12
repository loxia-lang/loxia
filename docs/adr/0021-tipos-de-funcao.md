# ADR-0021 — Tipos de função nas anotações

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0020](0020-assinaturas-explicitas.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [`../../TODO.md`](../../TODO.md) §2,
  [`../../TIPOS.md`](../../TIPOS.md) §6,
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/parser.py`](../../src/parser.py), [`src/ty.py`](../../src/ty.py),
  [`src/checker.py`](../../src/checker.py), [`tests/test_parser.py`](../../tests/test_parser.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

Depois do T3a (assinaturas explícitas), faltava o caso mais comum de função como valor:
passar uma função para outra. `FnTy` já existia no checker (usado para métodos, builtins e
variáveis que recebem funções), mas **não havia sintaxe** para escrever esse tipo numa
anotação. `f: fn(Int) -> Int` dava `Expect type name.`.

Sem isso, o único escape era `Any`, que não checa aridade nem tipos:

```lox
fn aplicar(f: Any, x: Int) -> Int { return f(x); }
aplicar(dobro, 3);      # passa
aplicar(3, 3);          # também passa: Any não valida nada
```

O objetivo é o menor passo que torne callbacks checáveis, sem entrar em generics nem em
lambdas.

## Decisão

1. **Sintaxe**: `fn(T1, T2) -> R` é um tipo de função; `fn() -> R` não tem parâmetros.
   Tipos de função podem aparecer em parâmetro, retorno, campo, local e dentro de
   `List`/`Map`/uniões.
2. **Precedência**: a seta liga ao tipo de retorno, então `fn(Int) -> Int | Nil` devolve
   `Int | Nil`. Para tornar a **função** opcional, use parênteses:
   `(fn(Int) -> Int)?`; `display` imprime `(fn(Int) -> Int) | Nil`.
3. **Aridade exata na anotação**: `fn(Int, Int) -> R` aceita exatamente dois argumentos.
   Defaults não aparecem no tipo; um valor com defaults é aceito se o intervalo
   `[min_params, len(params)]` cobre a aridade prometida.
4. **Atribuição estrutural**:
   - parâmetros são **contravariantes**: a função real precisa aceitar tudo que o tipo
     esperado promete passar;
   - retorno é **covariante**: pode devolver um subtipo do prometido;
   - a promoção `Int → Float` existente vale dentro dos parâmetros/retorno;
   - `Any` continua sendo escape e desliga a checagem naquele ponto.
5. **Classe como construtor**: `Animal` (o valor da classe) é atribuível a
   `fn(String) -> Animal` quando o `init` bate. Não é preciso criar `Class[Animal]`; a
   assinatura do construtor já descreve o valor. Instância (`: Animal`) e classe
   (`Animal`) continuam coisas distintas.
6. **Nativas**: `len`, `str` e `repr` ganham assinatura (`fn(Any) -> Int`/`String`) para
   poderem ser passadas como função; `clock` e `range` já eram `FnTy`.
7. **Fora desta etapa**: lambdas, trailing closures, generics, `callable`, `fn` sem
   parênteses, sobrecarga e tipos de função que capturem variáveis de tipo. Funções
   passadas como valor precisam ser nomeadas.

O runtime não muda: funções já eram valores de primeira classe e tipos continuam apagados.

## Consequências

### Positivas

- Callbacks e funções de ordem superior passam a ser checáveis:

  ```lox
  fn aplicar(f: fn(Int) -> Int, x: Int) -> Int { return f(x); }
  fn dobro(n: Int) -> Int { return n * 2; }
  val y = aplicar(dobro, 3);
  ```

- O corpo de `aplicar` checa a chamada `f(x)` contra a assinatura prometida.
- Construtores podem ser passados como fábricas (`criar(Animal)`).
- Funções que retornam funções funcionam sem sintaxe nova.
- Mensagens mostram o tipo completo (`fn(Int) -> Int`) e distinguem classe de instância.

### Negativas / custos

- Sem lambdas, o callback precisa ser uma função nomeada; `map`/`filter` genéricos ainda
  não são expressáveis (falta T3b/generics).
- A variância com `Int → Float` e tipos apagados tem as mesmas limitações já documentadas:
  anotar `Float` não converte o valor em runtime.
- Passar uma classe declarada **depois** do uso pode ser recusado, porque a assinatura do
  `init` ainda não foi preenchida no `ClassInfo` (a pré-declaração de T3a cobre funções de
  topo, não membros de classe).
- A mensagem de união de função usa parênteses (`(fn(...) -> ...) | Nil`) para não ficar
  ambígua; é um detalhe a mais na leitura.
- `Any` continua sendo a válvula de escape e pode esconder erros de callback.

## Alternativas consideradas

| Alternativa | Por que não agora |
| --- | --- |
| `callable` / `fn` solto (sem assinatura) | Só diria “é chamável”; não checa aridade nem tipos, quase igual a `Any` com nome melhor |
| Igualdade exata de assinatura (invariante) | Recusaria `fn(Animal) -> Animal` onde `fn(Dog) -> Animal` serve e funções com defaults; variância padrão é mais útil e ainda segura |
| `Class[Animal]` como tipo separado | A assinatura do construtor (`fn(String) -> Animal`) já descreve a classe como valor; evita um tipo novo |
| Generics/lambdas nesta etapa | Escopo maior; T3b cobre generics e lambdas ficam para o M3 |
| Resolver só na chamada, sem tipo de função | Era o `Any` disfarçado; não dá contrato ao parâmetro |

## Como verificar

- `tests/test_parser.py::test_parses_function_type_annotations` (sintaxe, `fn()`, `?` com
  parênteses, retorno de função);
- `tests/test_checker.py`:
  - `test_function_type_parameter_and_return_are_clean`;
  - `test_function_type_rejects_wrong_signature`;
  - `test_function_type_rejects_non_function`;
  - `test_function_type_checks_callback_body`;
  - `test_function_type_accepts_class_as_constructor`;
  - `test_function_type_is_contravariant_in_params_and_covariant_in_return`;
- `make check` verde.

Critério para revisar: quando lambdas, generics ou traits entrarem; se a variância
causar confusão em código real; ou se `Class[...]` for necessário para algo que a
assinatura do construtor não cobre.
