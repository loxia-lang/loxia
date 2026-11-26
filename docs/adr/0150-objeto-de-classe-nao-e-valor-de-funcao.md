# ADR-0150 — Objeto de classe não é valor de função

- **Status:** accepted
- **Data:** 2026-11-26
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (portão e I1–I4),
  [ADR-0044](0044-identidade-classe.md) (identidade de classe em runtime),
  [ADR-0048](0048-abi-classes-l5.md) (ABI de classes),
  [ADR-0059](0059-i4-check-limpo-compila.md) (check limpo compila),
  [ADR-0144](0144-any-dinamico-exige-estreitamento.md) (`Any`),
  [ADR-0147](0147-valores-de-funcao-assinatura-runtime.md) (valores de função),
  [ADR-0107](0107-adiados-e-nao-objetivos.md) (gatilho de reabertura), issue
  [#219](https://github.com/loxia-lang/loxia/issues/219) e
  [#247](https://github.com/loxia-lang/loxia/issues/247)
- **Implementação:** `loxia_core/semantics/type_ops.py` (`assignable`),
  `loxia_core/semantics/checker.py` (`_mismatch_message`),
  `tests/cases/class_object_value.lx`, `tests/cases/errors/class_object_to_fn.lx`,
  `tests/cases/errors/class_object_in_fn_map.lx`, `tests/test_checker.py`

## Contexto

A issue [#219](https://github.com/loxia-lang/loxia/issues/219) pede uma grafia para "o
objeto de classe" (`Type[C]`), `is`/`as` sobre ele e construção dinâmica, para que um
registro de classes em `Any`/`Map[String, Any]` consiga construir depois do lookup. A
investigação mostrou que o problema real é outro:

1. O checker **já aceitava** `ClassObjectTy` onde se espera `FnTy` (`val f: fn(...) = Circle`,
   um objeto de classe num `Map[String, fn(...)]`, um objeto de classe como argumento).
2. Mas em runtime um objeto de classe é um ponteiro de descritor, não um `LoxClosure`:
   `f is fn(...)` era `false` (o valor não tem `fn_type`) e guardá-lo num container de
   `fn(...)` fazia o binário ler o descritor como closure — **segfault** (exit 139) com
   `--check` limpo, enquanto o tree-walk funcionava. I1 e I4 quebrados por um programa
   limpo.
3. Tornar objeto de classe um valor de função **de verdade** custa caro: o binário não tem
   tag em valor de função (os dois são `i8*`), então ou se boxea/taggeia todo valor de
   função (ABI), ou se adiciona o tipo nominal `Type[C]` para o call site saber que aquilo
   é classe — e aí a construção dinâmica ainda pede um `dynctor` no descritor (args
   boxeados, regra de override de `init`).
4. **Nenhum consumidor real**: não há um caso sequer no corpus, em `std/`, em `examples/`
   ou na suíte do livro usando classe onde se espera `fn(...)`. O idioma de
   registro/fábrica já funciona com uma lambda por classe
   (`"circle": fn(r: Int) -> Shape { return Circle(r) }`), e a identidade de classe já
   funciona com `==` (`m["c"] == Circle`).

Pelo portão do [ADR-0014](0014-identidade-e-invariantes.md), a ausência não dói: é simetria
com outra linguagem. Recusar é parte do trabalho.

## Decisão

**1. Objeto de classe é um valor nominal, não um valor de função.** Ele é chamável quando o
tipo é o próprio objeto de classe (`val f = Circle; f(3)`), comparável por identidade
(`C == D`, `m["c"] == Circle`) e imprimível (`print(Circle)` → `Circle`). Ele **não** é
atribuível a `fn(...)` em nenhuma posição: inicialização anotada, atribuição, argumento,
retorno, campo ou elemento de container.

**2. O checker dá a remediação no diagnóstico.** "Expected a function ..., found the class
C. Class objects aren't function values; drop the annotation or wrap the construction in a
function."

**3. O que já funcionava continua:** `val f = Circle; f(...)`, `==`, `print`, `Any` guardando
classe (comparação por identidade) e a fábrica explícita por lambda.

**4. `Type[C]`, `is`/`as` para objeto de classe e construção dinâmica ficam adiados** — o
gatilho está no [ADR-0107](0107-adiados-e-nao-objetivos.md) e o desenho no apêndice, para
não ser redescoberto.

**5. Rebinding de classe continua** ([ADR-0044](0044-identidade-classe.md)): `Base =
OtherBase as Any` é aceito (a suíte oficial reatribui uma superclasse). O canto em que o
`Any` não guarda classe — o binário imprime o descritor antigo e o tree-walk imprime o
valor — é limitação registrada na issue
[#247](https://github.com/loxia-lang/loxia/issues/247).

## Consequências

### Positivas

- O crash deixa de existir: o programa do `Map[String, fn(...)]` com um objeto de classe
  passa a ser erro de check (exit 65) nos dois motores, em vez de segfault no binário.
- `is fn(...)` deixa de mentir: ou o valor é uma função (e o teste responde), ou o checker
  recusa a atribuição.
- Sem sintaxe nova, sem tipo novo, sem ABI nova e sem custo no caminho quente. Nenhum caso
  do repositório que funcionava de verdade se perde.

### Negativas / custos

- `val f: fn(...) = C` deixa de compilar. Era um acidente da erasure (o slot guardava o
  descritor, não a função); o caminho explícito agora é a lambda ou `val f = C`.
- Não existe identidade nominal no sistema de tipos (`Type[C]`); "é exatamente a classe C?"
  continua sendo `==`, e `K is C` segue `false` (o valor não é instância).
- A issue [#219](https://github.com/loxia-lang/loxia/issues/219) fecha sem a grafia pedida.

### Neutras

- `LoxClass`, `ClassObjectTy` e a representação de classe não mudam; nenhum arquivo de
  runtime é tocado.
- O canto do rebinding ([#247](https://github.com/loxia-lang/loxia/issues/247)) continua
  aberto, com repro, opções e aceitação registrados.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `Type[C]` exato (como `Class<C>` do Java) | Com semântica exata, `k is Type[C]` é sempre verdadeiro e `k()` é `C()`; o único conteúdo dinâmico é o `as` vindo de `Any`, que já é `==`. Compra sintaxe para não acrescentar poder. |
| `Type[C]` inclusivo (subclasse) | Resolveria o registro, mas exige descritor com `dynctor` (args boxeados), regra de override de `init` (hoje o checker não compara `init` de subclasse) e um kind novo no matcher; 2–3 semanas de ABI nova sem consumidor. Adiado. |
| E explícito: `C as fn(...)` / `is fn(...)` com thunk por classe | Viável e sem ABI (thunk no registro de classes), mas é uma feature de ~1 semana sem programa real; recusada pelo ADR-0014. Fica no apêndice. |
| E implícito (conversão dirigida por tipo) | O tree-walk é type-erased e não tem os tipos esperados em `evaluate`; exigiria refatorar o interpretador e viola I2 (coerção implícita). |
| `Type` cru (apagado) | Força o dispatch dinâmico que motivou a recusa (o binário não distingue classe de função), e o resultado de `K()` volta como `Any`. |
| Manter o accept atual e só recusar no lowering (PENDING) | O tree-walk continuaria funcionando e o binário falharia: I1 quebrado por declaração, que é pior que corrigir o tipo. |

## Apêndice — desenho adiado (para não redescobrir)

- **Exato vs inclusivo:** a decisão central. Exato é `==`; inclusivo (Python `type[C]`) é o
  que serve a fábrica heterogênea.
- **Inclusivo:** o descritor ganha um ponteiro `dynctor` `(LoxValue* args, int64 argc) -> void*`
  por classe (aloca o layout estático, roda inicializadores de campo, desemboxa cada
  argumento pelo tipo do próprio `init`, chama `init`, exige campos). O call site de
  `Type[C]` boxea os args pela assinatura de `C`; o checker precisa garantir
  `assignable + same_rep` entre `C.init` e `D.init` de toda subclasse (`init` não passa por
  `_check_overrides` hoje). Matcher: kind `O<id>` (tag 5 = classe) com identidade (ou
  `lox_is_instance` para inclusivo). Classes locais e genéricas ficam fora.
- **E explícito:** um thunk por classe (`lox.thunk.C(env, args...) -> lox.ctor.C(args...)`,
  `display` = nome da classe, `signature` = assinatura do `init`), registrado em
  `lox_register_class` como `{descriptor, thunk}`; `as fn(...)` valida pelo matcher (tag 5 +
  assinatura) e devolve o thunk; o tree-walk devolve um `LoxClassThunk` cacheado na classe
  (mesma identidade, `str`/`repr` iguais). `is fn(...)` responde pela assinatura do `init`.
  Remove a coerção implícita e deixa `as fn(...)` como a conversão explícita.

## Como verificar

- `tests/cases/class_object_value.lx` (l6, diferencial): `val f = Circle; f(3)`, `==`,
  `print`, `Any` + `==` e a fábrica por lambda nos três canais.
- `tests/cases/errors/class_object_to_fn.lx` e
  `tests/cases/errors/class_object_in_fn_map.lx`: erro de check com a remediação; o segundo
  era o segfault.
- `tests/test_checker.py::test_class_object_is_not_a_function_value` e
  `test_class_object_in_a_variable_is_callable`.
- `make check` (I1, I4 e determinismo verdes).

**Revisitar quando:** aparecer um programa real que precise construir a classe escolhida em
runtime (registro/fábrica heterogênea) e não se resolva por fábrica explícita. Aí a issue de
decisão escolhe entre o `Type[C]` inclusivo e o E explícito acima.
