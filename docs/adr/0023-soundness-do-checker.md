# ADR-0023 — Soundness do checker: retorno, campos e override

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0018](0018-narrowing.md), [ADR-0022](0022-lambdas.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [`../../TODO.md`](../../TODO.md) §2,
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

O checker era bom em inferir locais e checar argumentos, mas aceitava programas que
falham em runtime ou que mentem sobre a assinatura:

```lox
fn f() -> Int { print 1 }          # --check ok; em runtime devolve nil
```

```lox
class C {
  var x: Int
  init() {}                        # --check ok; runtime: Field 'x' must be initialized.
}
```

```lox
class A { f(x: Int) -> Int { return x } }
class B(A) { f(x: String) -> String { return x } }   # --check ok; override incompatível
```

Esses casos não são “feature faltando”: são buracos de confiança. Para o LLVM, o codegen
precisa poder assumir que o tipo declarado é verdadeiro.

## Decisão

### 1. Retorno em todos os caminhos

Funções e métodos com retorno **não-nil** precisam retornar em todos os caminhos:

```lox
fn f(flag: Bool) -> Int {
  if (flag) { return 1; }
  # erro: Function 'f' must return Int on all paths.
}
```

- Tipos nilables (`Int | Nil`), `Any`, `Never` e `<error>` ficam de fora da exigência.
- `init` não entra (devolve a instância).
- `return;` em função/método com retorno não-nil é erro (`Expected Int, found Nil.`).
- O mesmo `_body_always_returns` usado por lambdas passou a valer para funções/métodos.
  Laços são conservadores: `while (true) { return 1 }` ainda exige um `return` alcançável
  fora do laço.

### 2. Inicialização de campos

Todo campo **sem inicializador** precisa ser atribuído em **todos os caminhos** do `init`:

- campo com `= valor` conta como inicializado antes do `init`;
- atribuição `this.x = ...` é rastreada por um dataflow simples;
- `if`/`else` usa interseção dos conjuntos de campos atribuídos;
- `return` antecipado exige que os campos já estejam atribuídos;
- laços (`while`/`for-in`) não garantem execução do corpo, então não contam como
  atribuição definitiva;
- função/lambda aninhada não conta (executa depois, quando chamada).

```lox
class C {
  var x: Int;

  init(flag: Bool) {
    if (flag) { this.x = 1; }
    else { this.x = 2; }        # ok
  }
}
```

```lox
class C {
  var x: Int;
  init(flag: Bool) {
    if (flag) { this.x = 1; }   # erro: falta o else
  }
}
```

### 3. Override compatível

Métodos de subclasse são comparados com o método correspondente da superclasse, usando a
mesma relação de tipos de função:

- parâmetros **contravariantes** (a subclasse pode aceitar mais);
- retorno **covariante** (a subclasse pode devolver um subtipo);
- defaults contam como intervalo de aridade;
- `init` fica de fora (construtor não é virtual).

A checagem roda **depois** de visitar todas as classes, então funciona mesmo se a
superclasse aparecer depois da subclasse no arquivo.

```lox
class A { f(a: Animal) -> Animal { return a; } }
class B(A) { f(a: Animal) -> Dog { return Dog(); } }   # ok: retorno covariante
```

## Consequências

### Positivas

- O checker deixa de aceitar funções que devolvem `nil` com tipo `Int`.
- Campo não inicializado vira erro de compilação, não surpresa em runtime.
- Override incompatível é detectado antes de gerar vtable/codegen.
- A checagem reusa `_body_always_returns`, `_assignable` e `FnTy`, sem um segundo sistema
  de tipos.
- Testes de regressão cobrem os três buracos.

### Negativas / custos

- **Conservador em laços**: atribuir um campo só dentro de `while`/`for-in` é recusado,
  mesmo que o laço sempre execute. É seguro; o usuário move a atribuição para fora ou usa
  inicializador.
- **`while (true)`**: função que só retorna dentro de um laço infinito é recusada; exige
  um `return` alcançável. Também é conservador.
- **Campos herdados**: o dataflow cobre os campos da própria classe. Campos da superclasse
  dependem de `super.init`; a checagem de que `super.init` foi chamado em todos os caminhos
  fica para depois.
- **Atribuição indireta**: `this.x = ...` dentro de expressão condicional/curto-circuito
  pode não ser reconhecida; o checker prefere recusar a aceitar errado.
- **Locais** não têm análise de inicialização definitiva; só campos e retorno.
- O checker ainda é opt-in (`--check`); quem não roda não ganha a garantia.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Deixar só o runtime checar campo/retorno | Erro tarde, sem stack trace e com codegen inseguro |
| Exigir inicializador em todo campo | Recusaria o padrão `init(nome) { this.nome = nome }` |
| Aceitar qualquer atribuição em qualquer ramo | Não é soundness; `init` vazio com atribuição morta passaria |
| Override com assinatura exata | Recusaria retorno covariante e defaults, que são seguros |
| Checar override só na ordem do arquivo | Subclasse antes da superclasse ficaria sem checagem |
| Dataflow completo de locais/`super.init` agora | Escopo maior; fica para a próxima rodada de soundness |

## Como verificar

- `tests/test_checker.py`:
  - `test_function_must_return_on_all_paths`;
  - `test_method_must_return_on_all_paths`;
  - `test_bare_return_in_non_nil_function_is_an_error`;
  - `test_init_must_initialize_every_field`;
  - `test_class_without_init_must_have_field_initializers`;
  - `test_init_can_assign_a_field_in_both_branches`;
  - `test_init_assigned_in_only_one_branch_is_an_error`;
  - `test_field_initializer_satisfies_initialization`;
  - `test_override_must_be_compatible`;
  - `test_override_can_covary_the_return`;
  - `test_override_is_checked_even_if_superclass_comes_later`;
- `make check` verde.

Critério para revisar: quando entrar narrowing com `is` (ADR futuro), checagem de
`super.init`/campos herdados, ou se os falsos positivos de laço incomodarem em código real.
