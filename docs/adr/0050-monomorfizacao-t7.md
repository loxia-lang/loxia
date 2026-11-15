# ADR-0050 — T7: monomorfização de funções e classes genéricas

- **Status:** accepted (T7a/T7b/T7c implementados; containers ficam no L6)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0027](0027-generics-t3b.md),
  [ADR-0040](0040-generics-classes-desenho.md),
  [ADR-0048](0048-abi-classes-l5.md), [ADR-0049](0049-any-boxeado-spike-l6.md),
  [`../../TODO.md`](../../TODO.md) §0/§2/§6.11
- **Implementação:** [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`src/backend/lower_generics.py`](../../src/backend/lower_generics.py),
  [`src/backend/lower_class_layout.py`](../../src/backend/lower_class_layout.py),
  [`src/backend/lower_class_codegen.py`](../../src/backend/lower_class_codegen.py),
  [`tests/cases/generic_functions.lox`](../../tests/cases/generic_functions.lx),
  [`tests/cases/generic_class.lox`](../../tests/cases/generic_class.lx)

## Contexto

O checker já infere `id[T]`, `Box(1)` e `Pair(1, "a")`, mas o backend não sabia **quais**
instanciações existem. Re-inferir no lowering duplicaria a fonte de verdade e poderia
produzir miscompile silencioso; era preciso o checker publicar as instanciações concretas.

O T7 foi separado dos containers do L6: `List`/`Map` exigem decisões de representação
próprias, mas funções e classes genéricas podem ser monomorfizadas agora.

## Decisão

### 1. O checker publica as instanciações

- `generic_fn_instances: dict[Call, GenericFnInstance]` guarda nome e argumentos de tipo
  concretos por chamada.
- `generic_class_sites: dict[Call, ClassTy]` guarda cada construção genérica, inclusive
  dentro de corpo genérico (com `TyVar` que o lowering substitui pelo contexto atual).
- `concrete_class_types()` devolve só instanciações sem `TyVar`.

O backend **não** re-infere tipos: consome esses registros.

### 2. Monomorfização unboxed

Cada instanciação vira uma função/layout próprio:

```text
id(1)     -> lox.id$Int
id("a")   -> lox.id$String
Box(1)    -> layout Box$Int
Box("x")  -> layout Box$String
```

- `Int`/`Float`/`Bool` continuam desboxados.
- Nome mangled determinístico, derivado de `display` do tipo.
- Cache por `(nome, type_args)`; a entrada é registrada antes de emitir o corpo para
  permitir recursão.
- A ABI de função de topo continua `(i8* env, params...)`.
- A ABI de classe/descritor/instância do ADR-0048 não muda; o layout especializado só
  ganha um nome interno.

### 3. Funções genéricas

- Chamada direta `id(1)` vira chamada direta para `id$Int`.
- O corpo é lowering com `_type_subst: nome do parâmetro -> Ty concreta`.
- Defaults/aridade são preenchidos no call site, como no L4.
- Função genérica **como valor** continua 65 (recorte do ADR-0027).
- Chamada genérica **dentro** de outro corpo genérico pode usar a substituição do contexto;
  se ainda restar `TyVar`, vira 65 explícito.

### 4. Classes genéricas

- Cada `ClassTy(nome, args)` concreto ganha um `ClassLayout` (`Box$Int`, `Pair$String$Int`).
- Campos, `init`, métodos e `this` são substituídos; vtable e construtor são por
  instanciação.
- `Pair.swap() -> Pair[B, A]` cria a instanciação de retorno quando o checker a publica.
- **Identidade de fonte:** o tree-walk apaga `T`; `print` usa o nome-fonte (`Box instance`) e
  o descritor guarda esse nome. Layouts internos permanecem mangled.
- Classe genérica como valor, herança genérica, métodos genéricos e `is/as` com argumentos
  continuam 65; `is Box` sem argumentos não foi promovido neste corte.

### 5. Limites explícitos

- `List`/`Map`/tuplas/enums/exceções continuam L6.
- Não há boxing de `T`.
- Não há monomorfização especulativa: só instanciações que o checker publica.
- O limite de instanciações e a política de recursão polimórfica continuam os do
  ADR-0027; estouro vira 65, nunca código "mais ou menos".

## Alternativas rejeitadas

- **Re-inferir no backend:** duas fontes de verdade; proibido pela convenção do projeto.
- **Erasure/boxing:** contraria o ADR-0027 e perderia o unboxed antes de existir dor real.
- **Híbrido mono + boxed agora:** complexidade sem caso de uso; o caminho boxed entra com
  `Any`/módulos.
- **Clonar AST por instanciação:** mais código e mais risco que o contexto de substituição.
- **HIR completa:** a extração + este passe resolveram o T7 sem HIR.

## Consequências

- O corpus ganha o nível `t7` (`generic_functions.lox`, `generic_class.lox`).
- `generics.lox` e `generic_lambda_value.lox` continuam `PENDING` (containers e valor
  genérico).
- O L6 pode reutilizar o registro para instanciar `List`/`Map` sem re-inferência.
