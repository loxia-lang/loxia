---
sources:
  - loxia_core/thir/**
  - loxia_core/semantics/thir_build.py
  - loxia_core/frontend/spans.py
  - tests/test_thir.py
  - tests/test_thir_docs.py
---

# THIR — a árvore tipada entre o checker e os motores

O THIR é o eixo do programa de motores ([ADR-0149](../adr/0149-motores-primarios-thir-e-congelamento.md) §2):
uma árvore **tipada, resolvida e sem açúcar sintático** que carrega a decisão semântica
uma vez só. O AST continua existindo para tooling (formatter, LSP, `ast_json`); o THIR é
o que o lowering (F2) e o `loxvm` (F3) consomem.

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
| `span` | todo nó | diagnóstico e stack trace no ponto certo (ADR-0075/0089) |
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
| `UNRESOLVED` | nome inexistente | o `--check` já reportou; vira panic site |

A ordem de `captures` é **canônica: por nome**. Dois produtores independentes (o Python de
hoje e o checker em Loxia da F6) chegam ao mesmo índice, e o snapshot não muda por causa de
ordem de travessia. Nome repetido na mesma função é ambiguidade de `env`: o produtor falha em
vez de escolher.

`Ref` não carrega `depth`. O `depth` do resolver existia para o motor caminhar o encadeamento
de escopos; com captura explícita por função, o encadeamento já está resolvido na lista.

### Declarações e IDs

Toda declaração ganha um `DeclId` inteiro, atribuído em pré-ordem determinística. Os ids
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
| `TRange` | `Range` | `a..b` meio-aberto (ADR-0007) |
| `TUnary` / `TBinary` / `TLogical` | operadores | `op` + `op_span` (site do panic) |
| `TConditional` | ternário | explícito na v1 |
| `TVar` / `TAssign` | `Variable` / `Assign` | `Ref` resolvido |
| `TCall` | `Call` | `paren_span` é o site de erro; `instance`/`class_instance` |
| `TGet` / `TSet` | acesso a campo | `optional` preservado |
| `TIndex` / `TIndexSet` | indexação | |
| `TThis` / `TSuper` | receptor | `super` leva o `Ref` do `this` léxico |
| `TIs` / `TAs` | teste/conversão | |
| `TMatch` | `Match` | arms com bindings próprios |
| `TMatchArm` | arm | `pattern` + `body` |
| `TPattern` | padrão | base de `TVariantPattern`, `TWildcardPattern`, `TLiteralPattern` |
| `TLambda` | lambda | `TFunction` aninhada |

`Grouping` **não** sobrevive: parênteses são sintaxe. `ErrorExpr`/`ErrorStmt` também não —
árvore recuperada não compila.

### Statements

`TStmt` é a base (só `span`). `TExprStmt`, `TVarStmt`, `TDestructureStmt`, `TBlock`, `TIf`, `TWhile`, `TForIn`, `TFnDecl`,
`TReturn`, `TBreak`, `TContinue`, `TClassDecl`, `TInterfaceDecl`, `TEnumDecl`, `TTry`,
`TRaise`, `TTypeAlias`.

`Import` não aparece: o loader o resolve antes do checkout.

### Módulo e declarações

`TModule` é a raiz: `statements`, `decls`, `instances`, `type_aliases`, `entry` e
`schema_version`. `TFunction` (função, método ou lambda), `TParam`, `TCapture`, `TField`, `TClass`,
`TInterface`, `TEnum`, `TEnumVariant`, `THandler`, `Decl`.

## O que o THIR **não** carrega (v1)

Estas são decisões explícitas, não esquecimentos:

- **nada de alvo**: nem valor de LLVM, nem offset, nem slot, nem bitmap. O layout de classe e
  de frame é derivado pelo motor a partir dos `Decl`/`TClass` (emenda da F2 ao ADR-0149 §2).
- **nada de desugaring de controle**: `for-in`, `match`, `?:`, `??`, `?.` continuam nós
  explícitos. Desugar é a v2; fazê-lo junto com a migração misturaria “mudei a fronteira” com
  “mudei o codegen” e mataria o gate de `.ll` byte a byte.
- **nada de resolução de alvo de chamada**: `kernel`, método de classe, closure e classe
  continuam sendo distinguidos pelo lowering. Isso é dívida declarada da v1, não contrato.
- **nada de CFG**: sem blocos, phi ou cleanup. Quem precisa disso é a IR de controle.

## Produtor

`loxia_core/semantics/thir_build.py::build_thir` é o **único** leitor das tabelas por
identidade de nó do checker (`types`, `flow_types`, instanciações genéricas). Ele não infere
tipo: copia a decisão do checker (I4). Lacuna de entrada vira `ty is None`, nunca um tipo
inventado.

Escopo e captura seguem a mesma regra do `captures` do backend (ADR-0046), agora num lugar
só: declaração no escopo de topo é `GLOBAL`, declaração interna é `LOCAL` da unidade dona, uso
de fora é `CAPTURE`, e binding capturado vira `cell`. `tests/test_thir.py` compara, caso a
caso do corpus, as capturas e a contagem de células com `analyze_captures` — a equivalência é
policiada enquanto as duas implementações coexistirem.

## Determinismo (I3)

- ids atribuídos em pré-ordem; nenhuma ordem de `set`/`dict` vaza;
- capturas em ordem canônica por nome;
- `type_aliases` ordenados por nome;
- spans vêm dos tokens, sem caminho absoluto inventado (o arquivo é o de exibição);
- construir duas vezes a partir da mesma árvore produz módulos **iguais**.

A serialização (JSON v1, schema versionado, snapshot com hash) entra na fatia seguinte desta
fase; o modelo é o mesmo que ela vai gravar.
