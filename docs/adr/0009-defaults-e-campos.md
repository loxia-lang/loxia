# ADR-0009 — Parâmetros default e campos declarados

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TIPOS.md`](../../TIPOS.md)
  (futuro: tipos de campo/default), [`../spec/sintaxe.md`](../spec/sintaxe.md),
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `src/frontend/parser.py`, `src/frontend/stmt.py`, `src/execution/lox_callable.py`,
  `src/execution/lox_function.py`, `src/execution/lox_class.py`, `src/execution/lox_instance.py`, `src/semantics/resolver.py`,
  `src/execution/interpreter.py`; casos em `tests/cases/default_params.lox`, `fields_*.lox` e
  `tests/cases/errors/{default,field,arity_default}*.lox`

## Contexto

A decisão estava em aberto: funções não tinham parâmetros opcionais (aridade era um número
fixo) e campos de classe nasciam dinamicamente em `this.x = ...`, sem `val`/`var`, sem
checagem e sem lugar para o type checker se apoiar. A decisão de herança
([ADR-0008](0008-heranca-class-parens.md)) já tinha reservado os parênteses da classe para
a superclasse, então campos ficam no **corpo**, não no cabeçalho.

## Decisão

### Parâmetros default

1. Sintaxe `param = expr` (com tipos, vira `param: Tipo = expr`). Obrigatórios vêm antes;
   um obrigatório depois de um opcional é erro de sintaxe.
2. **Só constantes na v1**: literal, `nil`, `true`/`false`, `-` de literal numérico e
   parênteses em torno disso. Sem chamadas, sem referenciar outros parâmetros.
3. A avaliação acontece **na chamada**, mas como o valor é constante isso é determinístico
   e sem o problema de default mutável do Python. Avaliação geral fica para depois.
4. **Aridade vira intervalo `[mín, máx]`**. Mensagens:
   `Expected at least 1 arguments but got 0.`,
   `Expected 1 to 2 arguments but got 3.` (aridade fixa mantém `Expected N arguments...`).
5. `init` com defaults define a faixa de aridade da classe; subclasse sem `init` herda a
   faixa da superclasse. `var` com default é permitido (o binding continua mutável).

### Campos declarados

1. Campos são declarados no corpo da classe com `val`/`var`:
   ```lox
   class Pessoa {
     val nome;
     var idade = 0;
   }
   ```
   `val` exige atribuição (inicializador constante ou `init`); `var` pode ter inicializador
   ou ser atribuído no `init`.
2. **Todo campo declarado tem que estar inicializado** ao fim do `init` (ou ter
   inicializador). Sem inicializador implícito `nil` — isso prepara o non-null do checker.
3. `val` só pode ser atribuído **dentro do `init`**, e a atribuição é aceita uma única vez
   em runtime; fora do `init` o resolver já reporta erro.
4. `var` é mutável em qualquer método. Atribuir a campo **não declarado** é erro
   (`Undefined field 'x'.`), inclusive fora da classe.
5. Inicializadores de campo são **constantes na v1**. Eles rodam na criação da instância,
   antes do `init`; depois do `init` o runtime verifica que todos os campos foram
   inicializados.
6. Herança: campos são herdados; redeclarar um campo (no mesmo corpo ou na subclasse) é
   erro. Campo com o mesmo nome de método também é erro. `val` herdado não pode ser
   reatribuído; `var` herdado pode.
7. Não há campo dinâmico nem `val`/`var` implícito: a declaração é obrigatória. "Classe
   imutável" é só uma classe com todos os campos `val`.

## Consequências

### Positivas

- Aridade flexível sem overloading e sem o default mutável do Python.
- Campos viram offsets fixos no futuro LLVM e dão base para o checker (nomes e mutabilidade
  conhecidos em compile-time).
- `val` de campo com atribuição única elimina uma classe de bug; campos não declarados
  deixam de ser silenciosos.
- `this` continua implícito; não existe `self`.

### Negativas / custos

- **Breaking change**: `class Ponto {}; p.x = 1` não funciona mais; golden cases, exemplos e
  README foram migrados. Campos dinâmicos agora exigem declaração.
- Ainda não há tipos nos campos/defaults; o checker virá depois e vai completar a regra
  (`val nome: String`).
- Defaults só constantes limitam casos como `= list()`/`= agora()`; ficam para a evolução
  com avaliação na chamada.
- Atribuição de `val` no `init` é checada pelo resolver (fora do init) e pelo runtime
  (dupla atribuição); o checker poderá apertar para "exatamente uma vez" no fluxo.

### Neutras

- `Param` ganhou `default`; `Class` ganhou `fields`; `LoxCallable` trocou `arity()` por
  `min_arity()`/`max_arity()`.
- O parser valida constantes sintaticamente (default e inicializador de campo).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Default avaliado na declaração (Python) | armadilha clássica de default mutável compartilhado |
| Default avaliado na chamada desde já | mais poder, mas exige escopo/ordem e IR extra; v1 não precisa |
| Campos no cabeçalho (Kotlin) | colidiria com os parênteses da herança (ADR-0008) |
| Manter campos dinâmicos | sem base para tipos/LLVM e sem `val` de campo |
| `var` sem inicializador vale `nil` | contraria o non-null por padrão planejado; erro é mais seguro |
| `override`/`field` keywords | superfície sem necessidade agora |

## Como verificar

- `tests/cases/default_params.lox`, `fields_val_var.lox`, `fields_inheritance.lox`;
- `tests/cases/errors/`: `default_not_constant.lox`, `required_after_optional.lox`,
  `arity_default_min.lox`, `arity_default_max.lox`, `field_immutable.lox`,
  `field_val_outside_init.lox`, `field_unknown.lox`, `field_uninitialized.lox`,
  `field_redeclare.lox`, `field_inherit_redeclare.lox`,
  `field_initializer_not_constant.lox`;
- `tests/test_interpreter.py` (classes, defaults, aridade), `tests/test_parser.py`;
- `make check`.

Critério para revisar: quando o type checker entrar (tipos de campo/default), quando
defaults gerais forem necessários, ou se `val` de campo precisar de regra de fluxo mais
fina.
