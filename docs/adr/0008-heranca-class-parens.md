# ADR-0008 — Herança com `class Dog(Animal)` e construtor `init`

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TODO.md`](../../TODO.md) §1/§11,
  [ADR-0009](0009-defaults-e-campos.md) (campos/defaults),
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `src/frontend/parser.py`; casos em `tests/cases/inheritance*.lox`,
  `super*.lox` e `tests/cases/errors/class_inherit_self.lox`,
  `superclass_not_class.lox`

## Contexto

O parser vinha do livro: `class B < A`. O `<` já significa comparação em expressões e a
sintaxe não é a mais legível; o TODO já registrava a intenção de trocar. Ao mesmo tempo,
queremos decidir onde ficam construtor e atributos:

- Python: `class Dog(Animal)` — parênteses guardam as **bases**, e o construtor é
  `__init__` com `self` explícito.
- Kotlin: `class Dog(val nome: String) : Animal(nome)` — parênteses guardam os
  **parâmetros do construtor**, `:` guarda a herança, `this` é implícito.

Os dois usos de parênteses são incompatíveis. Como o construtor da nossa linguagem já é
`init` e os campos nascem no corpo (`this.x = ...`), os parênteses depois do nome da classe
estão livres.

## Decisão

1. **Herança com parênteses**: `class Cachorro(Animal)` (uma única superclasse). Classe sem
   superclasse continua `class Cachorro { ... }`. O `<` é **removido**, sem alias.
2. **Construtor continua `init`**, sem parâmetros no cabeçalho da classe. Campos declarados
   ficam para [ADR-0009](0009-defaults-e-campos.md) **no corpo da classe** (opção B), não no
   cabeçalho — assim os parênteses nunca precisam ser reaproveitados.
3. **`this` implícito**, sem `self`: métodos não recebem o receptor como parâmetro.
4. **`super.init(...)` explícito** quando a subclasse define `init` (como Python); não há
   chamada automática. Subclasse **sem** `init` herda o `init` da superclasse (comportamento
   atual, mantido).
5. **Sobrescrita silenciosa**: não existe `override` agora; o type checker futuro pode
   avisar. Métodos e `init` são herdados por `find_method`.
6. **Herança simples** apenas; múltipla/mixins ficam para traits (P3).
7. **Sem `new`**: `Cachorro("Rex")` continua sendo a chamada do construtor.

## Consequências

### Positivas

- Sintaxe familiar a quem vem de Python, sem keyword nova e sem sobrecarregar `:`.
- Como o construtor fica em `init`, os parênteses têm um único significado para sempre.
- Reforça a decisão do ADR-0009: campos no corpo, não no cabeçalho.
- `this` implícito evita o ruído do `self` em cada método.

### Negativas / custos

- **Mudança incompatível**: `class B < A` deixa de funcionar; os golden cases, exemplos e
  docs foram migrados. Quem tiver código antigo precisa trocar.
- Abre mão de `class Pessoa(val nome: String)` no estilo Kotlin; se isso virar necessidade,
  a saída é migrar a herança para `extends` e liberar os parênteses.
- Sobrescrita silenciosa pode esconder erro de digitação (`falar` vs `fallar`); mitigável
  no checker/LSP.

### Neutras

- `classDecl` fica `"class" IDENTIFIER ("(" IDENTIFIER ")")? "{" function* "}"`.
- O parser não aceita mais `(` vazio nem múltiplas superclasses; a mensagem é
  `Expect superclass name.` / `Expect ')' after superclass.`

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `class B extends A` | deixaria parênteses livres para ctor estilo Kotlin, mas adiciona keyword e não é o que queremos agora |
| `class B : A` | `:` já é anotação de tipo e mapa; sobrecarga visual e contexto ambíguo |
| Manter `class B < A` | `<` binário confunde e o TODO já queria trocar |
| Aceitar `<` como alias temporário | duas sintaxes para a mesma coisa, sem data para remover |
| Parâmetros de construtor no cabeçalho (Kotlin) | colidiria com herança nos parênteses; campos no corpo resolvem |

## Como verificar

- `tests/cases/inheritance.lox`, `inheritance_init.lox`, `inheritance_override.lox`,
  `inheritance_super_init.lox`, `super.lox`, `super_with_this.lox`;
- `tests/cases/errors/class_inherit_self.lox`, `superclass_not_class.lox`,
  `super_*.lox`;
- `tests/test_parser.py` (`class B(A)`, `class B < A` é erro) e `tests/test_interpreter.py`
  (herança, `super`, `init`);
- `make check`.

Critério para revisar: se campos/parâmetros no cabeçalho (Kotlin) entrarem em pauta; se
`override` for exigido; ou se herança múltipla/traits entrarem no escopo.
