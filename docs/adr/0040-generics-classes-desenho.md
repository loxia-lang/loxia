# ADR-0040 — Classes genéricas (T6a): desenho

- **Status:** accepted (MVP implementado; métodos/herança genérica pendentes)
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0020](0020-assinaturas-explicitas.md),
  [ADR-0027](0027-generics-t3b.md), [ADR-0031](0031-backend-nativo.md),
  [ADR-0034](0034-t3c-revertido.md), [ADR-0038](0038-traits-nominais.md),
  [`../../TIPOS.md`](../../TIPOS.md), [`../../TODO.md`](../../TODO.md) §9

## Contexto

O T3b cobre funções genéricas (`fn id[T]`), mas classes não têm parâmetros de tipo. O M5
depende do T6a, e o codegen está pausado no L4 até o M5 fechar; L6 (layouts) precisa saber
o que é uma instância de classe genérica. Este ADR fixa o **desenho** e o recorte mínimo;
a implementação é a próxima fatia e não muda o backend agora.

## Decisões

1. **Sintaxe e escopo.** `class Box[T] { ... }` e `class Pair[K, V] { ... }`; os parâmetros
   ficam no escopo de campos, métodos, `init` e `this`. Tipos podem aninhar
   (`Box[Box[Int]]`, `List[T]`, `Map[String, T]`, `fn(T) -> U`). O parser já tem
   `_type_parameters()` para funções; a classe reusa.
2. **`ClassTy` ganha argumentos.** `ClassTy(name, args=())`; `display` vira `Box[Int]`.
   A alternativa de separar `GenericClassTy`/`ClassInstanceTy` mudaria ~20 usos sem ganho;
   o default `()` preserva todo o código atual. `ClassObjectTy` continua só com o nome (o
   construtor infere os argumentos).
3. **Invariante.** `Box[Int]` não é `Box[Float]` nem `Box[Any]`: campos `var` e `set(T)`
   tornam covariância/covariância-com-`Any` unsound. `Any` segue escape só no topo; dentro
   dos argumentos, a comparação é exata.
4. **Inferência no construtor.** `Box(1)` infere `Box[Int]` unificando os parâmetros do
   `init` com os argumentos (vars frescas por chamada, como no T3b). Tipo esperado
   pré-binda (`val b: Box[Int] = Box()`); sem `init` e sem esperado, ou com `Any`, o erro
   pede anotação. `Box` sem argumentos em posição de tipo é erro de aridade — não existe
   `Box` = `Box[Any]`.
5. **`this` e `init`.** `this` é `ClassTy(name, type_params)` (não `ClassTy(name)`), e o
   `init` devolve `ClassTy(name, type_params)`; a chamada devolve a instância com os
   argumentos inferidos.
6. **Fora do MVP.** Métodos genéricos (`fn map[U]`; função livre cobre), herança de classe
   genérica (`class C(Box[Int])`), constraints/bounds, type application explícita
   (aplicar argumentos explicitamente a uma chamada), `is`/`as Box[Int]` (runtime apaga
   `T`, sem reificação), varância
   declarada e classe genérica como valor de função. `class Box[T]` herdando de `Base` não
   genérica é permitido.
7. **Runtime e backend.** Erasure total no tree-walk: `LoxClass`/`LoxInstance` não mudam;
   `is`/`as` com argumentos de classe são recusados. O backend continua rejeitando
   `class` com 65; no L6, monomorfiza por `ClassTy(name, args)` (nome mangled,
   `Box$Int`) e registra as instâncias que o checker viu.

## Impacto no código

| Arquivo | Mudança |
| --- | --- |
| `loxia_core/frontend/ty.py` | `ClassTy.args`; `display` com argumentos |
| `loxia_core/frontend/stmt.py` | `Class.type_params` |
| `loxia_core/frontend/parser.py` | `_class_declaration` lê `[T, ...]`; `_generic_type` devolve `ClassTy(name, args)` para classes (validação sai do parser e vai para o checker); erro em superclasse genérica |
| `loxia_core/frontend/ast_printer.py` | sufixo de type params no dump |
| `loxia_core/semantics/checker.py` | `ClassInfo` com params/nomes; `_declare_type_params`; push/pop no escopo da classe; `_resolve_type` com aridade; `_infer_class_construction`; `_class_bindings` + substituição em campos/métodos/`this`/`init`; `_assignable`/`_unify`/`_substitute`/`_occurs`/`_unbound_type_vars` sobre `args`; guards de `is`/`as` |
| `loxia_core/execution/interpreter.py` | guards de `is`/`as` com `ClassTy` que tem args; resto inalterado |
| `loxia_core/execution/type_test.py` | sem mudança (guards impedem `ClassTy` com args) |
| `loxia_core/backend/lower.py` | sem mudança; `Class` já cai no fallback 65 |
| testes | parser, checker, interpreter, backend e golden `generic_class.lox` |

## Plano de implementação

1. **Parser/AST/tipos**: `class C[T]`, `Class.type_params`, `ClassTy.args`, printer,
   erro de superclasse genérica; testes de parser.
2. **Checker — declaração**: `ClassInfo` com params, escopo de tipos, `this`/`init`,
   resolução/aridade de `Box[Int]`.
3. **Checker — inferência**: `_infer_class_construction` e unificação do `init`;
   `Box(1)`, `Pair(1, "a")`, `val b: Box[Int] = Box()`; erros.
4. **Checker — membros e relações**: substituição em campos/métodos, `_assignable`
   invariante, `_unify` de `ClassTy`, interop com funções genéricas (ex.: `fn first[T]`
   recebendo `Box[T]`).
5. **Runtime/backend**: erasure e guards; teste de rejeição 65.
6. **Testes/golden/docs** e fechamento do T6a no TODO.

## Implementação (MVP)

O MVP foi implementado: `class C[T]`, `ClassTy(name, args)`, inferência no construtor,
`this`/`init` parametrizados, substituição em campos/métodos e guards de `is`/`as`.
Continuam pendentes os itens abaixo.

## Em aberto (depois do MVP)

- Métodos genéricos (`fn map[U]`) e composição com os params da classe.
- Herança de `Box[Int]` (AST/runtime name-based) e overrides que usam `T`.
- Varância declarada, bounds/constraints, `is`/`as` reificado.
- Política de `Any` na inferência e monomorfização no L6.

## Alternativas rejeitadas

- **Split `GenericClassTy`/`ClassInstanceTy`:** churn em assignable/is/as/display/unify sem
  ganho no MVP.
- **`Box` = `Box[Any]` silencioso:** aceitaria `Box[Int]` onde se espera `Box[String]`;
  contra I2 e a invariância de `List`/`Map`.
- **Covariância:** unsound com campos mutáveis/`set(T)`.
- **Herança genérica agora:** `Class.superclass` é um nome; exigiria mudar AST/parser/
  runtime e substituir a cadeia inteira.
- **Métodos genéricos agora:** instanciação por chamada + receptor; a função livre
  genérica resolve o caso de uso.
