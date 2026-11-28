---
sources:
  - loxia_core/thir/**
  - loxia_core/semantics/thir_build.py
  - loxia_core/frontend/spans.py
  - loxia/engine.py
  - loxia/cli_args.py
  - schema/thir-v1.json
  - tools/thir_schema.py
  - tools/thir_snapshot.py
  - tests/thir/manifest.json
  - tests/thir_support.py
  - tests/test_thir.py
  - tests/test_thir_docs.py
  - tests/test_thir_serialization.py
  - tests/test_thir_schema.py
  - tests/test_thir_snapshot.py
  - tests/test_lowering_ll.py
  - tests/ll/manifest.json
  - tools/lowering_snapshot.py
---

# THIR — a árvore tipada entre o checker e os motores

O THIR é o eixo do programa de motores ([ADR-0149](../adr/0149-motores-primarios-thir-e-congelamento.md) §2):
uma árvore **tipada e resolvida** que carrega a decisão semântica uma vez só (sem `Grouping`;
o açúcar de controle fica explícito por decisão, não por adiamento
([ADR-0156](../adr/0156-sem-desugaring-no-thir.md)), ver §O que o THIR não carrega). O AST
continua existindo para tooling (formatter, LSP, `ast_json`); o THIR é o que o lowering (F2) e
o THIR eval (F3) consomem.

```
source .lx
   │ front
   ▼
AST ─────────────► ast_json (tooling/LSP/formatter)
   │ checker (dona dos tipos)
   ▼
THIR ────────────► JSON v1 (snapshot/contrato entre build-time e runtime)
   ├─ lowering   → control IR → LLVM → binário
   └─ THIR eval  → efeitos (REPL, --interpret, oráculo)      [F3]
```

O THIR **não** é CFG nem SSA. Se um construto precisar de fluxo (phi, blocos, cleanup),
ele desce para a [IR de controle](control-ir.md) — esse é o sinal de que o THIR está no
lugar certo.

## O que o modelo carrega

| Campo | Onde | Por quê |
| --- | --- | --- |
| `ty` (fluxo) | todo `TExpr` | narrowings: `if (x != nil)` estreita o **uso**, não a declaração |
| `storage_ty` | todo `TExpr` | tipo declarado/sem narrowing (ADR-0045) |
| `span` | todo nó de expressão/statement/padrão/declaração | diagnóstico e stack trace no ponto certo (ADR-0075/0089); `TModule` e `TInstance` não têm site próprio |
| `op_span` | todo operador (`TUnary`/`TBinary`/`TLogical`/`TIs`/`TAs`/`TRange`) | span **do token do operador** (não do operando): é o site de erro/panic que o motor emite; sem ele o `.ll` mudaria de byte |
| `Ref` | `TVar`/`TAssign`/`TThis`/`TSuper` | binding resolvido; nada de busca por nome no motor |
| `Decl.cell` | `Decl` | o binding é célula compartilhada (ADR-0046) |
| `TFunction.captures` | função/lambda | o `env` que o motor monta, em ordem canônica |
| `TInstance` | `TCall`/módulo | site genérico já inferido; monomorfização é do backend |

### Bindings

Um `Ref` responde “onde este nome vive”, e só isso:

| `Storage` | Significado | Como o motor acha |
| --- | --- | --- |
| `LOCAL` | frame da função corrente | slot do `Decl` no frame |
| `CAPTURE` | célula carregada no `env` | índice do `Decl` em `TFunction.captures` |
| `GLOBAL` | escopo de topo | slot global do `Decl` |
| `BUILTIN` | nome pré-declarado sem declaração no fonte | pelo nome (kernel, namespace nativo, enum/classe de prelude) |
| `UNRESOLVED` | nome inexistente | o `--check` já reportou; vira panic site |

`BUILTIN` cobre `print`, `len`, `Int`, `math`, `Result`, `Exception` e afins: o checker os
declara no escopo global (`Checker.global_scope`), não há `Decl` no programa. Confundir
`BUILTIN` com `UNRESOLVED` seria transformar `print(1)` em panic site — foi assim que a
revisão da fatia 1 pegou o bug.

A ordem de `captures` é **canônica: por nome**. Dois produtores independentes (o Python de
hoje e o checker em Loxia da F6) chegam ao mesmo índice, e o snapshot não muda por causa de
ordem de travessia. Nome repetido na mesma função é ambiguidade de `env`: o produtor falha em
vez de escolher.

`Ref` não carrega `depth`. O `depth` do resolver existia para o motor caminhar o encadeamento
de escopos; com captura explícita por função, o encadeamento já está resolvido na lista.

### Declarações e IDs

Toda declaração ganha um `DeclId` inteiro. A ordem é determinística mas não é
simplesmente a ordem do fonte: primeiro vêm as declarações de **topo** que o checker
pré-declara (`fn`, `class`, `interface`, `enum`, na ordem do arquivo), depois o restante na
ordem de visita (parâmetros, `val`/`var`, lambdas, padrões, `this`, métodos). Os ids
identificam bindings, funções, classes, interfaces, enums, lambdas e `this` — é o que
substitui `dict[Expr, Ty]` e `id(statement)`. Ids são estáveis **entre execuções** (mesma
entrada ⇒ mesmos ids), não entre edições: mudar a ordem de declaração renumera, e isso
aparece no diff do snapshot — que é o comportamento desejado para um contrato revisável.

## Nós

### Expressões

| Nó | Substitui | Observação |
| --- | --- | --- |
| `TConst` | `Literal` | valor + tipo; `nil` é `None` |
| `TInterp` | `InterpolatedString` | partes literais e expressões |
| `TList` / `TMap` / `TTuple` | literais de container | ordem do fonte preservada |
| `TRange` | `Range` | `a..b` meio-aberto (ADR-0007); `op_span` do `..` |
| `TUnary` / `TBinary` / `TLogical` | operadores | `op` + `op_span` (site do panic) |
| `TConditional` | ternário | explícito na v1 |
| `TVar` / `TAssign` | `Variable` / `Assign` | `Ref` resolvido |
| `TCall` | `Call` | `paren_span` é o site de erro; `instance`/`class_instance` |
| `TGet` / `TSet` | acesso a campo | `optional` preservado |
| `TIndex` / `TIndexSet` | indexação | |
| `TThis` / `TSuper` | receptor | `super` leva o `Ref` do `this` léxico |
| `TIs` / `TAs` | teste/conversão | `op_span` do `is`/`as` (site do `R1011`) |
| `TMatch` | `Match` | arms com bindings próprios |
| `TMatchArm` | arm | `pattern` + `body` + `span` |
| `TPattern` | padrão | base de `TVariantPattern`, `TWildcardPattern`, `TLiteralPattern` |
| `TLambda` | lambda | `TFunction` aninhada |

`Grouping` **não** sobrevive: parênteses são sintaxe. `ErrorExpr`/`ErrorStmt` também não —
árvore recuperada não compila.

### Statements

`TStmt` é a base (só `span`). `TExprStmt`, `TVarStmt`, `TDestructureStmt`, `TBlock`, `TIf`, `TWhile`, `TForIn`, `TFnDecl`,
`TReturn`, `TBreak`, `TContinue`, `TClassDecl`, `TInterfaceDecl`, `TEnumDecl`, `TTry`,
`TRaise`, `TTypeAlias`.

`TDestructureStmt` carrega o **padrão**, não uma lista achatada: `TDestructurePattern` é a
base de `TNamePattern` (um nome) e `TTuplePattern` (grupo), e o aninhamento de
`val (a, (b, c))` é significativo — o motor desestrutura por posição. O tipo de cada nome é o
do **elemento**, distribuído a partir da anotação ou do tipo do inicializador; copiar a
anotação da tupla para todos os nomes daria representação errada.

O `Decl` do `TForIn` é um só: a declaração é estática. O ambiente novo por iteração (para a
closure ver o valor daquela volta) é decisão do motor, não do contrato.

`Import` não aparece: o loader o resolve antes do checkout.

### Módulo e declarações

`TModule` é a raiz: `statements`, `decls`, `instances`, `type_aliases`, `entry` e
`schema_version`. `TFunction` (função, método ou lambda; `abstract` distingue assinatura de
interface de default de corpo vazio), `TParam`, `TCapture`, `TField`, `TClass`,
`TInterface`, `TEnum`, `TEnumVariant`, `THandler`, `Decl`.

## O que o THIR **não** carrega

Estas são decisões explícitas, não esquecimentos:

- **nada de alvo**: nem valor de LLVM, nem offset, nem slot, nem bitmap. O layout de classe e
  de frame é derivado pelo motor a partir dos `Decl`/`TClass` (emenda da F2 ao ADR-0149 §2).
- **nada de desugaring de controle**: `for-in`, `match` (e os padrões), `?:`, `??`, `?.` e
  interpolação continuam explícitos — **decisão final, não adiamento**
  ([ADR-0156](../adr/0156-sem-desugaring-no-thir.md)). Desugar fixaria uma estratégia de
  lowering para todos os motores e exigiria tipos/builtins que a linguagem não tem (iterador,
  teste de variante, `stringify` de linguagem): `match` não tem expressão “é a variante V”
  (o payload só existe como binding), `for-in` usaria `nil` como sentinela e perderia os
  *version checks* de `List`/`Map`, e o backend deixaria de especializar o loop por tipo
  (`for i in 0..n` viraria iterador alocado). O THIR eval avalia o nó; o lowering especializa.
- **nada de resolução de alvo de chamada**: `kernel`, método de classe, closure e classe
  continuam sendo distinguidos pelo lowering. Isso é dívida declarada da v1, não contrato.
- **nada de CFG**: sem blocos, phi ou cleanup. Quem precisa disso é a IR de controle.

## Produtor

`loxia_core/semantics/thir_build.py::build_thir` é o **único** leitor das tabelas por
identidade de nó do checker (`types`, `flow_types`, instanciações genéricas). Ele não infere
tipo: copia a decisão do checker (I4). Lacuna de entrada vira `ty is None`, nunca um tipo
inventado.

Nomes que o checker pré-declara sem `Decl` no fonte (builtins, namespaces nativos) viram
`BUILTIN`; referências para frente de topo (`fn a` que chama `fn b` declarada depois) são
resolvidas por uma pré-declaração de top-level que espelha o checker — sem ela, um programa
check-limpo nasceria cheio de `UNRESOLVED` e o motor emitiria panic sites falsos.
`tests/test_thir.py` policia os dois casos e exige **zero** `UNRESOLVED` no corpus declarado.

Escopo e captura seguem a mesma regra do antigo `captures` do backend (ADR-0046), agora num
lugar só: declaração no escopo de topo é `GLOBAL`, declaração interna é `LOCAL` da unidade
dona, uso de fora é `CAPTURE`, e binding capturado vira `cell`. Com o lowering já consumindo o
THIR, não há segunda implementação a comparar: a equivalência é policiada pelo gate `.ll`
(269 casos byte a byte) e por `tests/test_captures.py`, que fixa captura/célula no produtor.

## Determinismo (I3)

- ids atribuídos na pré-declaração de topo e depois na ordem de visita do fonte; nenhuma
  ordem de `set`/`dict` vaza — `TModule.instances` é ordenada por `(nome, display dos argumentos)`
  porque o checker entrega as classes genéricas num `set`;
- capturas em ordem canônica por nome;
- `type_aliases` ordenados por nome;
- spans vêm dos tokens, sem caminho absoluto inventado (o arquivo é o de exibição);
- construir duas vezes a partir da mesma árvore produz módulos **iguais**.

## Serialização (JSON v1)

`loxia_core/thir/serialize.py` é a única implementação do formato: `to_payload`/`from_payload`,
`dumps` (legível, para revisão) e `canonical` (compacto e ordenado, para hash).

```text
{"k":"TModule","schema_version":1,"source_path":"tests/cases/x.lx","entry":3,
 "decls":[{"k":"Decl","id":1,"name":"x","ty":{"k":"prim","name":"Int"}, ...}],
 "instances":[{"k":"TInstance","name":"Box","type_args":[...]}],
 "type_aliases":[],
 "statements":[{"k":"TFnDecl","fn":{...}}]}
```

- **Todo registro tem `k`** com o nome da classe (`TBinary`, `Decl`, `Ref`), e campos com o
  nome do dataclass. Enums (`Storage`, `DeclKind`, `TokenType`) viram o nome
  (`"CAPTURE"`, `"MINUS"`).
- **`Ty` é estruturado, não `display()`**: `{"k":"list","element":{"k":"prim","name":"Int"}}`.
  Um motor não deve precisar de um parser de tipo para ler o contrato; `display()` continua
  sendo a forma de diagnóstico (ADR-0129), não a de máquina.
- **`TClass`/`TField` não carregam layout** (ADR-0154); `ClassTy.token` (posição no fonte)
  não é serializado — não é semântica.
- **Versão**: `schema_version` viaja no topo e só muda em quebra; `from_payload` recusa
  versão desconhecida. O schema versionado é [`schema/thir-v1.json`](../../schema/thir-v1.json),
  gerado do modelo por `tools/thir_schema.py` (`make thir-schema`) e validado com
  `jsonschema` nos casos de contrato — o campo é `const: 1`, então o próprio schema recusa
  outra versão.
- **v1 congelado na F2** (2026-11-28): `op_span` e `abstract` entraram ainda durante a
  fase, antes do fechamento. A partir daqui, campo obrigatório novo ou remoção é **v2**
  (o schema tem `additionalProperties: false`, então não há extensão compatível de campo).
  **v2 é evolução de schema, não desugaring**
  ([ADR-0156](../adr/0156-sem-desugaring-no-thir.md)).
- **Determinismo**: `sort_keys` em todo objeto, listas na ordem canônica do modelo, nada de
  `set`/`dict` derivado. O mesmo programa produz os mesmos bytes, inclusive entre processos
  com `PYTHONHASHSEED` diferentes (`tests/test_thir_serialization.py`).
- **Caminhos**: `source_path` e `span.file` são o caminho de exibição (o que o CLI recebeu).
  O consumidor não deve passar caminho absoluto: o snapshot e o I3 vivem de caminho relativo.

### Snapshot

`tests/thir/manifest.json` guarda o sha256 da forma canônica do THIR de cada caso do corpus
declarado; `tools/thir_snapshot.py --check` (e o teste de corpus) recusam divergência.
Atualizar é revisão consciente: `make thir-snapshot` regrava e o diff de hashes diz
exatamente quais casos o contrato mudou — "consertar para passar" é proibido. Para ler o
contrato de um caso, `loxia build <caso> --emit=thir` imprime o JSON (o THIR é verboso por
causa dos spans, então goldens completos versionados seriam ruído, não revisão).

## O lowering consome o THIR (fatia 3, concluída)

O lowering recebe o `TModule`, não a AST. O contrato foi **só a fronteira**: mesmo
programa, mesmo `.ll` byte a byte, congelado em `tests/ll/manifest.json`
(`make ll-snapshot`) e policiado por `tests/test_lowering_ll.py`; o backend não importa
`loxia_core.frontend.expr`/`stmt` (`tests/test_thir_boundary.py`).

### Por que foi atômico

A árvore é uma só. No instante em que `Lowerer` recebe `TModule`, todo handler recebe nós
THIR; não existe nó híbrido e um dispatch duplo (AST **ou** THIR) reintroduziria as duas
rotas que o [ADR-0154](../adr/0154-fronteira-do-thir.md) elimina. Por isso o port é **um
commit** (mais um de triagem de docs): o gate `.ll` de 269 casos cobre a árvore inteira.

### Métrica de complexidade (A9), com a receita

Medido em `7561f36` (pré-port) e no HEAD, com o comando ao lado — número sem comando não
conta:

| métrica | antes | depois | comando |
| --- | --- | --- | --- |
| leituras de side table no backend (`self.` nas 6 tabelas) | 46 | **0** | `git grep -E "self\.(types\|flow_types\|depths\|generic_instances\|generic_class_sites\|generic_classes)\b" <rev> -- loxia_core/backend \| wc -l` |
| arquivos do backend que importam `frontend.expr`/`frontend.stmt` | 21 | **0** | `git grep -l -E "from loxia_core\.frontend\.(expr\|stmt)" <rev> -- loxia_core/backend \| wc -l` |
| `backend/captures.py` | 402 linhas | apagado | `git show 7561f36:loxia_core/backend/captures.py \| wc -l` |
| diff do port | — | +1883/−1695 em 35 arquivos | `git diff --shortstat 7561f36..0c04be3` |
| diff da fatia (port + triagem + converge) | — | +2112/−1802 em 36 arquivos | `git diff --shortstat 7561f36..HEAD` |

O dispatch continua sendo `isinstance` (40 sítios em `_expr`/`_stmt`), agora sobre nós `T*`;
o ganho não é "menos branches", é **uma** árvore e nenhuma tabela por identidade de nó.

Renomes mecânicos:

| AST | THIR |
| --- | --- |
| `expr.operator` (`.type`, `.line`) | `op` + `op_span` |
| `expr.paren.line` | `paren_span.start.line` |
| `expr.bracket.line` | `bracket_span.start.line` |
| `expr.keyword.line`, `stmt.keyword.line` | `span.start.line` |
| `expr.name.lexeme` (variável/atribuição) | `Ref.name` (+ `Ref.storage`) |
| `expr.name.lexeme` (campo) | `TGet`/`TSet.name` + `name_span` |
| `stmt.name.lexeme` | `Decl` do id (`decl_table(module)`) |
| `stmt.type_annotation` | `Decl.ty` / `TParam.ty` / `TField.ty` |
| `param.default` | `TParam.default` (template avaliado no call site) |
| `self.types[expr]` | `TExpr.storage_ty` |
| `self.flow_types[expr]` | `TExpr.ty` |
| `self.depths.get(expr)` | `Ref.storage` + índice em `TFunction.captures` |
| `Function.abstract` | `TFunction.abstract` (assinatura de interface × default de corpo vazio) |
| `Function.doc`, `fn_token`, `params_end`, `arrow` | não usados no backend |

### O que morreu

- `self.types`, `self.flow_types`, `self.depths` e as tabelas por identidade de nó;
- `loxia_core/backend/captures.py` (a decisão vira `Decl.cell` + `captures`), coberto por
  `tests/test_captures.py` no produtor;
- a pilha `_scopes` por **nome** continua existindo no lowering (o layout de frame é dele,
  não do THIR): a **classe** do binding vem de `Ref.storage`, e o slot é achado pelo nome no
  escopo — o resolver garante unicidade por escopo (`E2001`), então nome e `DeclId` coincidem
  na prática. Um `Ref` que aponte para fora do escopo vivo é captura (`CAPTURE`), não `LOCAL`.

### `op_span` em todos os operadores

O port revelou uma lacuna do modelo: o lowering emitia a posição do **operador** em
constantes do `.ll` (`lox_range_new`, `lox_float_to_int`, `lox_panic`). `TUnary`/`TBinary`
já tinham `op_span`; `TLogical`, `TIs`, `TAs` e `TRange` ganharam o mesmo campo, preenchido
pelo produtor com o token do operador. Sem ele o gate byte a byte não fecha (e o `R1011`
do `as` mudaria de coluna no stderr). O snapshot do THIR (`tests/thir/manifest.json`) e o
schema (`schema/thir-v1.json`) mudaram de propósito nessa fatia.

### Fidelidade de diagnóstico

`TClass.superclass_span` carrega o site do nome da superclasse, que é a linha usada pelo
refusal `Inheritance from 'X' is not supported by the backend yet`
(`lower_class_layout.py`). Com isso o port não perde nenhum site de erro que o lowering
usa hoje; não há outra lacuna conhecida de span. O `op_span` dos operadores (acima) é o
mesmo contrato: o site do erro é o token do operador.

### Ordem dos commits do port

1. `lower.py` — entrada `lower(module)`, dispatch de statements/expressões, aritmética;
2. `lower_variables` — slots/células por `DeclId`;
3. `lower_functions` — ABI de closure, `TFunction`, defaults;
4. `lower_calls` — kernel × closure × método × classe, `TInstance`;
5. optionais/`Any` (`lower_optionals`);
6. containers/strings/bytes/tuplas/range/math;
7. classes/instâncias/generics (`lower_class_codegen`, `lower_instances`, `lower_generics`);
8. exceções/enums/`match` (`lower_exceptions`, `lower_enums`), remoção de `captures.py` e
   das assinaturas antigas (`driver`, `engine`).

