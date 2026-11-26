# ADR-0146 — `is`/`as` para interface

- **Status:** accepted
- **Data:** 2026-11-25
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0080](0080-interfaces-nominais-implementacao.md) (interfaces nominais
  e ABI B2), [ADR-0144](0144-any-dinamico-exige-estreitamento.md) (`Any` exige estreitamento),
  [ADR-0055](0055-l6-any-casts.md) (`Any` boxeado), [ADR-0025](0025-is-e-narrowing.md) /
  [ADR-0029](0029-conversoes-math.md) (`is`/`as`), [ADR-0048](0048-abi-classes-l5.md) (ABI de
  classes), issue [#213](https://github.com/loxia-lang/loxia/issues/213)
- **Implementação:** `loxia_core/semantics/checker.py` (`_validate_is_type`,
  `_validate_as_target`, `visit_as_expr`, `_resolve_test_type`),
  `loxia_core/execution/type_test.py`, `lox_class.py`/`lox_instance.py`
  (`implements_interface`), `loxia_core/execution/interpreter.py` (`_runtime_type`),
  `loxia_core/backend/lower_class_codegen.py` (kind `J<id>`), `runtime/objects.c`
  (`lox_implements_interface`, parse `J`), `tests/cases/any_interface.lx`,
  `tests/cases/errors/any_interface_cast.lx`, `tests/cases/errors/interface_cast_static.lx`

## Contexto

O [ADR-0144](0144-any-dinamico-exige-estreitamento.md) tornou o estreitamento obrigatório
para acesso dinâmico em `Any`; a mensagem do `E3025` manda usar `is`/`as`. O
[ADR-0080](0080-interfaces-nominais-implementacao.md) tinha deixado `is`/`as` com interface
fora da v1 e o checker recusava com `Interface types aren't supported in 'is'/'as' yet.`
(`E1005`/`E3013`). Isso deixava um buraco: um `Any` que guarda uma instância que implementa
uma interface só podia ser estreitado para a classe concreta — o polimorfismo via `Any`
(plugin, visitor, método default) era impossível, e a mensagem do `E3025` apontava para um
caminho que o checker recusava.

A fase B2 do ADR-0080 já tinha colocado no descritor de classe a tabela `interface_count` /
`interfaces` (`interface_id` + `itab`) usada pelo despacho de métodos. O dado de runtime
para responder "esta instância implementa `I`?" já existia; faltava expô-lo ao `is`/`as`.

## Decisão

1. **`is I` e `as I` são aceitos** para uma interface nominal `I`. A interface continua sendo
   um tipo, não um valor; o valor em runtime é sempre a instância concreta.
2. **Checagem de runtime pela tabela de interfaces** do descritor de classe (efetivas: as
   próprias mais as herdadas da superclasse). O matcher de tipos ganhou o kind
   **`J<id>`** (`kind = -4`), com o mesmo `interface_id` do despacho de métodos; o payload é
   o ponteiro da instância. Não há tag nova em `LoxValue`, campo novo no descritor nem
   mudança de ABI: `lox_implements_interface` percorre a tabela existente.
3. **`is` estreita para `InterfaceTy`.** `if (x is I)` refina o caminho para `I`, então
   `x.m()` resolve o método da interface (inclusive default) normalmente. A resolução do
   alvo usa o tipo já validado (`_resolve_test_type`), sem emitir diagnóstico duplicado.
4. **Regra estática do `as`:** de uma classe concreta que **não** implementa `I`, o checker
   recusa (`Can't cast C to I.`, `E3013`); de `Any`, de união ou de outra interface, o cast
   é aceito e checado em runtime (`R1011: Can't cast value to I.` se falhar). O tree-walk
   usa o mesmo `matches_type`, então os dois motores concordam no ponto da falha.
5. **Assinatura apagada:** a checagem é nominal (implementa/não implementa), não compara a
   assinatura dos métodos em runtime (os tipos são apagados). A conformidade de assinatura
   continua sendo responsabilidade do checker na declaração `implements` (ADR-0080).
6. **Sem mudança no despacho:** métodos default, `itab`, herança de interface pela
   superclasse e a ordem determinística continuam como no ADR-0080.
7. **Nomes importados e containers:** o loader renomeia a interface no tipo (`mod$lib$I`),
   mas o token de `implements` guarda o nome de exibição; o `LoxInterface` guarda os dois
   (canônico e exibição) e `implements_interface` aceita ambos. A normalização
   `ClassTy→InterfaceTy` é recursiva em `List`/`Map`/tupla/união, então `is List[I]` e
   `is Map[K, I]` funcionam.
8. **`??` em união de não-escalares:** o checker usa o tipo comum entre o lado não-nulo e
   o direito (`I | Nil ?? C` → `I`; `C? ?? D` → `C` com `D` subclasse) e o lowering preserva
   `interface_name` no phi; sem isso o backend recusava a união (`E4001`) e o uso direto
   perdia o despacho de interface (#221). Diagnósticos de tipos importados mostram o nome
   local (último segmento do nome canônico, #222).

## Consequências

### Positivas

- A mensagem do `E3025` passa a ser acionável para interfaces: `(a as I).m()` e
  `if (a is I)` funcionam no binário e no tree-walk.
- `Any` pode guardar uma implementação de interface e usá-la polimorficamente, sem conhecer
  a classe concreta.
- Sem custo de ABI: o descritor já tinha a tabela; o matcher só a consulta.

### Negativas / custos

- `as` entre interfaces é checado em runtime (não há relação estática entre interfaces
  nominais); um cast de `I` para `J` pode falhar em runtime.
- Interfaces genéricas continuam fora (ADR-0080); `is`/`as` com `I[Int]` não existe.
- Função e objeto de classe continuam sem `is`/`as`; a issue #213 segue aberta para eles.

### Neutras

- O kind `-4`/`J<id>` é interno ao matcher e ao cache de tipos; o texto do tipo só aparece
  em `--emit=ll`/diagnóstico interno.
- A tabela de interfaces continua a mesma do despacho; nenhum campo sintético de exceção ou
  layout de instância muda.

## Alternativas

- **Tag `INTERFACE` em `LoxValue`** e um valor de interface separado: quebraria o princípio de
  que o valor é a instância concreta e exigiria mudança de ABI/GC; recusado.
- **Só cast estático** quando a origem é uma classe concreta: não resolve `Any`, que é o
  caso que o ADR-0144 abriu; recusado.
- **Comparar assinatura em runtime**: os tipos são apagados; só a aridade de função estaria
  disponível (e função é outro alvo). Fica para o PR de funções.
- **Estender o descritor com um bitmask de interfaces**: desnecessário; a tabela existente
  responde à pergunta e já é usada pelo despacho.

## Como verificar

- `tests/cases/any_interface.lx` (l6, diferencial): `is`/`as` em `Any`, interface como tipo
  estático, interface→interface, método default, subclasse, `List[I]`/`Map[String, I]` e
  `is` falso.
- `tests/test_modules.py::test_interface_importada_is_as_nos_dois_motores`: interface
  importada, `is`/`as` e paridade tree-walk × binário.
- `tests/cases/interface_union_optional.lx` (l6, diferencial): `I | Nil ?? C`,
  `List[Int] | Nil ?? [..]` e o uso direto do resultado; `test_modules` cobre o diagnóstico
  de tipo importado (`Can't cast value to Named.`).
- `tests/cases/errors/any_interface_cast.lx` (l6, diferencial): `Any` com `Int` → `as I`
  falha em runtime com a mesma mensagem/exit nos dois motores.
- `tests/cases/errors/interface_cast_static.lx`: classe que não implementa → erro de checker.
- `tests/test_checker.py::test_interface_is_and_as_are_accepted` e
  `test_interface_as_from_class_that_does_not_implement_it`.
- `make check` (diferencial + I4 + determinismo).
