# ADR-0046 — L4: closures, células e valores de função

- **Status:** accepted (backend L4 implementado)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0009](0009-defaults-e-campos.md) (defaults),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1–I3), [ADR-0018](0018-narrowing.md),
  [ADR-0020](0020-assinaturas-explicitas.md) (ordem de declaração),
  [ADR-0021](0021-tipos-de-funcao.md) (`FnTy`), [ADR-0022](0022-lambdas.md) (lambdas),
  [ADR-0026](0026-freeze-1.0.md), [ADR-0031](0031-backend-nativo.md) (contrato do backend),
  [ADR-0033](0033-inferencia-t3c-t4.md) (T4), [ADR-0034](0034-t3c-revertido.md),
  [`../../TODO.md`](../../TODO.md) §0.1/§6, [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `loxia_core/backend/captures.py`, `loxia_core/backend/lower.py`,
  `loxia_core/backend/llvm_ir.py`, `runtime/runtime.c`, `tests/test_backend.py`,
  `tests/test_captures.py`, `tests/corpus_manifest.py`

## Contexto

O L0–L3 compila funções de topo com chamada direta, mas não funções como valor: `print
soma`, `fn` local, `return f`, `f()` com `f` variável e lambdas fecham com exit 65. O
tree-walk já implementa tudo isso e é o oráculo do I1
([ADR-0002](0002-tree-walk-como-oraculo.md)): closure é `LoxFunction` com referência ao
`Environment` de declaração, `val`/`var` capturados compartilham o **mesmo** binding
(mutação visível em `makeCounter`), função local é declarada quando o statement executa e
`print` de função é `<fn nome>`/`<lambda>`.

O L4 tem quatro casos `PENDING` (`closures`, `closure_static_scope`, `functions`,
`local_function`) e precisa de decisões que mudam o contrato do backend: representação de
variável capturada, ABI das funções, conversão de função para valor, defaults/aridade e o
que fazer com diagnósticos. Sem fechar isso antes, cada uma dessas escolhas reaparece no
meio do codegen e o nível L0–L3 corre risco de regressão.

Decisões já tomadas que restringem o espaço:

- o backend não re-infere tipos: consome o que o checker publica
  ([ADR-0031](0031-backend-nativo.md), [ADR-0045](0045-narrowing-representacao.md));
- defaults só existem em **chamada direta** de função nomeada e são constantes
  ([ADR-0009](0009-defaults-e-campos.md));
- função genérica **não é valor** ([ADR-0027](0027-generics-t3b.md));
- `Any`, `List`/`Map` e classes ainda não têm representação até L5/L6.

## Decisão

### 1. Sem HIR: lowering direto + passe de captura

O L4 continua `AST → LLVM` com a normalização leve do ADR-0031. A única análise nova é um
passe **de captura** (`loxia_core/backend/captures.py`), que descobre quais bindings locais são
usados por funções aninhadas e quais funções cada closure precisa capturar. Ele não muda a
AST nem vira camada de IR.

HIR-lite fica registrada como gatilho: se o `lower.py` começar a duplicar o
`interpreter.py` (L5/L6, ex.: classes + `this` + `super`), a normalização sobe de nível
antes de continuar. Não se paga HIR completa agora só para closures.

### 2. Células só para variáveis capturadas

Um binding local é `alloca` (pilha) enquanto ninguém o captura. Quando o passe de captura
marca um `Param`, `Var` ou `Function` local como capturado, o binding vira uma **célula**
no heap (arena): o valor mora em `lox_alloc_cell()` e o `alloca` guarda o ponteiro para a
célula. Leitura/atribuição passam a fazer `load`/`store` na célula.

Consequências:

- `var i` mutado por closure é compartilhado, como no tree-walk;
- `val` capturado também vira célula (uniformidade); não há cópia por valor;
- variáveis não capturadas continuam desboxadas e no caminho quente do L2/L3;
- o env de uma closure guarda **ponteiros de célula** (`i8*`), não valores.

Rejeitadas: boxar toda variável local (custo em todo programa e sem ganho) e a cadeia de
ambientes estilo clox (reescreve o acesso a variáveis de L2–L3 e paga em todo frame).

### 3. ABI uniforme: todo `fn` de usuário recebe `env`

Toda função de usuário — de topo, local ou lambda — compila como:

```llvm
define <ret> @lox.<nome>(i8* %env, <params>...)
```

`env` é `null` quando a função não captura nada e aponta para uma struct de células quando
captura. O `main` gerado continua `i32 ()`, sem `env`.

Uma **closure** é um valor `i8*` para uma struct alocada na arena:

```llvm
{ i8* fnptr, i8* env, i8* display }
```

- `fnptr` é a função LLVM com a assinatura acima;
- `env` é a struct de células (ou `null`);
- `display` é a string determinística **já formatada** (`<fn f>` ou `<lambda>`), usada por
  `print`/`str`/`repr`/interpolação; nunca contém endereço.

Chamada indireta carrega `fnptr`/`env`, faz `bitcast` para o tipo de função e chama com
`env` como primeiro argumento. Chamada direta a nome conhecido usa `info.ir` e o `env`
carregado do valor da função (para recursão local).

Rejeitada a alternativa de só funções que capturam receberem `env`: obrigaria a distinguir
dois tipos de função em todo valor e a gerar adaptadores; um parâmetro a mais é mais barato
que duas ABI.

### 4. Funções locais e lambdas

Uma declaração `fn` dentro de bloco é uma closure criada **quando o statement executa**,
guardada no binding local (célula, porque a própria função pode se referenciar para
recursão). O corpo é emitido uma vez, com nome LLVM determinístico
(`lox.<nome>.<contador>`); a closure é recriada a cada execução da declaração.

`fn` de topo também é um valor: a assinatura LLVM é pré-declarada (para recursão mútua),
mas o **binding global** só recebe a closure quando o statement é executado. Assim
`print f(); fn f()...` continua erro de runtime (exit 70, `Undefined variable 'f'.`), como
no interpretador; não há hoisting.

Lambdas (`fn(x) => ...`/`fn(x) { ... }`) entram com **tipo concreto** publicado pelo
checker (`FnTy`). Lambda genérica (`GenericFnTy`, T4 sem contexto) é rejeitada com 65:
função genérica não é valor (ADR-0027) e o backend ainda não tem monomorfização como valor
(é L6).

### 5. Tipos de função vêm do checker

O lowering passa a consumir `checker.storage_types` (ADR-0045), não uma inferência
própria. Um valor de função carrega um `FnSig` (parâmetros, retorno e `min_params`)
derivado do `FnTy`; `_variable`, `_assign`, `return` e chamadas comparam o `FnSig` além do
`ValueType`. Tipos não representáveis (`Any`, `List`, classes, uniões com `Nil`, `TyVar`)
falham com 65.

Assinaturas de função com defaults têm `min_params < max`; elas podem ser chamadas
diretamente, mas **não podem virar valor** (ver item 6).

### 6. Defaults e aridade

- **Chamada direta** a função nomeada continua preenchendo defaults no call site, como no
  L2; a aridade é `[min, max]` e a mensagem de erro é a do interpretador.
- **Função com defaults como valor** (`val f = soma; f(1)`, passar `soma` como argumento,
  retornar `soma`, `print soma`) é **exit 65** no L4: `Functions with default parameters as
  values are not supported by the backend yet.` O caso fica `PENDING` e a limitação é explícita.
- **Chamada indireta** (variável/parâmetro/retorno) exige aridade exata `len(params)` e
  usa `min_params`/`max_params` só para a mensagem; sem descriptor de defaults em runtime.
- O corpus L4 atual não usa defaults como valor (`functions.lox` imprime uma função sem
  defaults; `closures.lox` retorna uma função sem defaults).

Rejeitado o descriptor com `min/max/defaults` + wrappers por aridade: é maquinário e casos
de borda (contravariância, defaults parcialmente aplicados) que não doem no corpus; se
doer, entra num ADR de follow-up.

### 7. `print` de função

`print`, `str`, `repr` e interpolação de um valor de função usam o campo `display` da
closure:

- função nomeada: `<fn f>`;
- lambda: `<lambda>`;
- método ligado (L5): `<fn metodo>`, quando o layout de classe existir.

O runtime ganha `lox_print_function` e `lox_str_from_function`; ambos copiam a string
determinística, sem imprimir o endereço da closure.

### 8. Spans e stack trace ficam fora do L4

O L4 mantém o contrato atual de erro: `lox_panic(linha, msg)`, stderr `msg\n[line N]` e exit
70. Spans/caret e stack trace **não entram neste nível**: eles mudam o stderr de todos os
erros, exigem frames no tree-walk e no runtime C e não são necessários para closures.

A decisão vira um ADR próprio **antes do L5/L6** (a fila do TODO registra isso). Até lá, o
I1 continua comparando stdout, stderr e exit code no formato atual.

### 9. Memória

> **Atualização (2026-11-14):** a arena foi substituída pelo GC Boehm no
> [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md). `lox_alloc_cell`/`lox_alloc_env`/
> `lox_alloc_closure` continuam sendo a fronteira; o teto e a promessa do I1 estão no
> ADR-0074.

Envs, células e closures usam a arena existente (`lox_alloc`), sem `free`, com teto e
`lox_panic` determinístico. Novos pontos de alocação são isolados em
`lox_alloc_cell`/`lox_alloc_env`/`lox_alloc_closure`, então trocar a arena por Boehm segue
sendo mudar o corpo de `lox_alloc` (ADR-0031, decisão 7). Sem endereço, timestamp, ordem de
hash ou caminho na saída (I3).

### 10. Escopo do L4

Entram: funções locais, lambdas com tipo concreto, closures com captura/mutação, funções
como valor (parâmetro, retorno, variável, `print`/`str`), chamada indireta, ordem de
declaração de topo e limites explícitos de defaults.

Ficam fora: defaults como valor, função genérica como valor, `T?` de função (L2.5/L5),
classes/métodos (`this`/`super`, L5), `Any`/`List`/`Map`, exceções no nativo e stack trace.

## Consequências

### Positivas

- O I1 do L4 cobre os quatro casos que já existem e os novos casos de valor de função.
- O caminho quente de variáveis não capturadas continua desboxado; o custo de célula é
  local às capturas.
- Uma ABI só para funções simplifica chamadas indiretas, recursão local e o L5
  (`this` pode ser mais um parâmetro/`env` sem inventar outra convenção).
- O contrato de erro não muda; spans/stack trace não contaminam a implementação de L4.

### Negativas / custos

- Toda função ganha um parâmetro `env` e toda chamada de topo passa a carregar a closure
  do global (mais uma carga e uma checagem de nulo); L7 pode otimizar chamadas diretas.
- Funções com defaults usadas como valor ficam explicitamente sem suporte no L4; é uma
  lacuna de I1 fora do corpus declarado.
- Funções não capturadas ainda alocam uma closure na arena (uma por criação/execução da
  declaração); sem free, programas que criam closures em loop crescem a arena.
- O passe de captura duplica parte da lógica lexical do resolver e precisa acompanhar
  novos nós de escopo (classes, `for-in`) nos próximos níveis.

### Neutras

- `storage_types` passa a ser usado pelo lowering; `types` (fluxo) continua só para
  diagnóstico/testes.
- O nome LLVM de funções locais/lambdas usa contador determinístico, não a linha/coluna.
- `print` de função deixa de ser constante de compilação e passa a ler o `display` da
  closure (mesmo resultado, agora funciona para variáveis).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| HIR-lite/HIR completa agora | custo alto e risco de regressão em L0–L3 sem dor demonstrada; gatilho fica registrado |
| Todas as locais em célula | alocação e indireção em todo acesso, inclusive fora de closures |
| Cadeia de ambientes estilo clox | reescreve o modelo de variáveis do L2/L3 e paga em todo frame |
| Captura só por valor | quebra `makeCounter` (mutação compartilhada) e a semântica do tree-walk |
| Só funções que capturam recebem `env` | duas ABIs e adaptadores em todo valor de função |
| Descriptor com defaults em runtime | maquinário grande para um caso fora do corpus; fica para follow-up |
| Içar funções de topo | mudaria a semântica do interpretador/ADR-0020 e exigiria mudar o tree-walk |
| Spans/stack trace no L4 | muda stderr/I1 de todos os erros e não é pré-requisito de closure |
| Recusar lambdas no L4 | o checker já publica `FnTy` concreto e o custo é pequeno depois de funções locais |

## Como verificar

- `tests/corpus_manifest.py`: `closures`, `closure_static_scope`, `functions` e
  `local_function` saem de `PENDING` para `LEVELS["l4"]`.
- `tests/test_backend.py`: casos diferenciais novos para função como parâmetro/retorno,
  `print`/`str`/interpolação de função, lambda com captura, mutação de capturado e ordem de
  declaração (`print f(); fn f()...` sai 70 com a mesma mensagem).
- `tests/test_captures.py`: marca como capturado o binding que o lowering vira célula;
  binding não capturado não é marcado; captura transitiva por função intermediária;
  top-level global não é capturado. O teste diferencial do L4 cobre a célula em runtime.
- `tests/cases/defaults_as_value.lox`: passa no `--check` e falha no backend com 65,
  documentado em `PENDING`.
- `make check` verde (ruff + mypy strict + pytest) e `make bench` sem regressão >1.35x.

## Critérios para revisitar

- Se defaults como valor doerem no corpus/L6, criar ADR de descriptor de aridade/defaults
  em runtime (ou wrappers por aridade) e promover o caso.
- Se o passe de captura começar a crescer para classes/`for-in`/`this`, promover a
  normalização do ADR-0031, decisão 10, para HIR-lite.
- Se a alocação de closure em loop doer (arena), avaliar reuso/escape analysis no L7.
- Spans/stack trace: ADR próprio antes do L5/L6; não misturar com o contrato de panic do
  L4.

## Referências

- Crafting Interpreters, cap. 10–11 (funções, closures, resolver) e cap. 25 (closures no
  clox).
- *Mapping High-Level Constructs to LLVM IR* — closures e representação de ambiente.
- [`../../TODO.md`](../../TODO.md) §6.6 (closures e classes) e §6.8 (L4).
- [`../spec/semantica.md`](../spec/semantica.md) — semântica de funções/lambdas.
