# ADR-0047 — L2.5: optionais escalares, `nil` contextual e unwrap seguro

- **Status:** accepted (backend L2.5 implementado)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0006](0006-int-float-separados.md) (`Int`/`Float`),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1–I3),
  [ADR-0018](0018-narrowing.md), [ADR-0024](0024-mutacao-monomorfica.md),
  [ADR-0031](0031-backend-nativo.md) (`T?` em `{i1, T}`),
  [ADR-0032](0032-narrowing-campos-indices.md),
  [ADR-0045](0045-narrowing-representacao.md) (`storage_types`),
  [ADR-0046](0046-closures-celulas-l4.md) (células), [`../../TODO.md`](../../TODO.md) §0.1/§6.3
- **Implementação:** `src/backend/lower.py`, `runtime/runtime.c`,
  `tests/test_backend.py`, `tests/corpus_manifest.py`, `tests/cases/variables.lox`

## Contexto

O L2 fechou sem `T?` e sem variável não inicializada (`variables.lox` está `PENDING l2`).
O tree-walk já trata `Int?` como `Int | Nil`:

```lox
var b: Int?;       # nil
print b;           # nil
b = 1 + 2;
print b;           # 3
if (b != nil) print b + 1;
```

O [ADR-0031](0031-backend-nativo.md), decisão 3, já escolheu a representação: **ponteiro
nulo para referência** e **`{i1, T}` para escalar** (sentinela não serve para `Float`
porque `NaN` é valor legítimo). O que falta é o contrato de codegen: onde `nil` ganha
representação, como o valor opcional entra/sai de variáveis, parâmetros, retornos e
células capturadas, e como o lowering consome o narrowing sem violar o ADR-0045.

Fatos que restringem a solução:

- tipos são apagados no tree-walk; uma variável `Int?` pode estar em qualquer estado,
  mas o checker só permite operações não opcionais depois de um refino;
- o narrowing ainda é **deliberadamente incompleto** (ADR-0045): `var` capturado por
  closure e aliasing não invalidam refinamentos; usar o tipo de fluxo para escolher
  representação abriria a porta para miscompile;
- células de closure hoje têm 8 bytes; `{i1, i64}`/`{i1, double}` têm 16;
- `var x;` sem anotação é erro do checker (`Can't infer type...`); `variables.lox` usa a
  forma anotada `var b: Int?;`.

## Decisão

### 1. Representação

- `Int?`, `Float?`, `Bool?` são `{i1, T}`: tag `i1` (1 = tem valor) + payload `T`.
- `String?`, instância opcional e outros tipos de referência serão **ponteiro nulo**
  quando o L5 chegar; o L2.5 implementa só os escalares.
- `nil` **não tem representação autônoma**: o literal é `Value(NIL)` e ganha forma no
  contexto (`_coerce`). `print nil` continua usando `lox_print_nil`; `nil` em variável
  sem tipo é rejeitado (não há tipo `Nil` de armazenamento).
- Células de closure passam a reservar `16` bytes (o maior `{i1, T}`); não se cria uma
  alocação por tipo de célula.

### 2. `var` sem inicializador

- `var x: T?;` é suportado: o slot nasce com `nil` e o tipo é o anotado.
- `var x;` (sem anotação) continua **erro de `--check`**: o backend nunca o recebe.
  O `TODO.md` fala em “`var x;`” como sinônimo de variável não inicializada; a forma
  suportada é a anotada.
- `var x: Int;` (não opcional) sem inicializador é check-clean mas ficaria com `nil` num
  slot `i64`; o L2.5 **rejeita com 65** (`Uninitialized variables of non-optional type
  are not supported by the backend yet.`) e o caso fica `PENDING`. Representar esse
  estado exigiria tratar toda variável não inicializada como opcional internamente, o
  que é L6 (caixa dinâmica).

### 3. Coerção nas fronteiras

Só existem quatro transições, e todas passam por `_coerce`:

| De | Para | Ação |
| --- | --- | --- |
| `nil` | `T?` | optional com tag 0 / ponteiro nulo |
| `T` | `T?` | optional com tag 1 + payload |
| `T?` | `T?` | identidade |
| `T?` | `T` | **unwrap checado** (tag 1; senão panic) |

As fronteiras são: inicializador/atribuição de variável, `return`, argumentos de chamada,
campos (L5) e valores de função com assinatura opcional.

### 4. Unwrap seguro, não narrowing otimista

O lowering **não** usa `types` (fluxo) para decidir representação. Quando uma operação
precisa de um `T` e recebe `T?`, emite a checagem da tag e só então extrai o payload:

- se a tag for 0, `lox_panic` no ponto (mensagem da operação, quando existir);
- se for 1, o payload segue desboxado.

Em código que o checker já estreitou, a checagem é redundante mas barata; é o preço de
não confiar num refino incompleto (ADR-0045). Uma otimização futura pode remover checks
onde houver prova de CFG/aliasing, mas não neste nível.

### 5. Operações observáveis

- `print`/`str`/`repr`/interpolação: tag 0 → `nil`; tag 1 → valor formatado.
- truthiness: só tag 0 é falsy (o payload `0`/`false` continua truthy).
- `==`/`!=`: `T? == nil` testa a tag; `T? == T` testa tag + payload; `T? == T?` testa
  tag + payload.
- `??`: tag 1 devolve o payload; tag 0 avalia o lado direito.
- `if`/`while`/`and`/`or`/ternário usam a truthiness e mesclam com `phi` quando preciso.
- Parâmetros/retornos/lambdas com `T?` usam `{i1, T}` na ABI; o `FnSig` carrega o
  `optional` do parâmetro/retorno.
- Closures podem capturar `T?`; a célula é de 16 bytes e o unwrap continua no uso.

### 6. Fora do L2.5

- `String?`, instância opcional, `?.` e `??` de referência entram no L5c.
- `fn(...)?` não entra agora.
- `val x = nil` (tipo `Nil` puro) continua 65; não há representação de variável `Nil`.
- `Any` boxeado e uniões com mais de um membro não-Nil ficam no L6.

## Consequências

### Positivas

- `variables.lox` sai de `PENDING` sem tocar no tree-walk.
- A representação `{i1, T}` mantém `Int`/`Float` desboxados no caminho não opcional.
- O unwrap checado impede miscompile quando o narrowing estiver errado; o pior caso é
  panic determinístico, não lixo.
- O mesmo `_coerce` serve para variáveis, parâmetros, retornos e células; o L5 reusa para
  referências nulas.

### Negativas / custos

- `Int?` ocupa 16 bytes e toda operação não opcional sobre um opcional paga uma checagem
  de tag mesmo depois do `if (x != nil)`.
- `var x: Int;` sem inicializador fica 65 até existir caixa dinâmica.
- Células de closure crescem de 8 para 16 bytes, mesmo para tipos não opcionais.
- O lowering fica maior: `TypeDesc` passa a carregar `optional` e as operações ganham
  caminho opcional.

### Neutras

- O checker não muda (exceto a documentação de que `var x;` exige anotação).
- `print nil` e `nil == nil` continuam sem representação opcional.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Sentinela em `Int`/`Float` | `NaN` é valor legítimo e não há sentinela livre em i64 |
| Caixa uniforme `T?` para tudo | dobra referências no caminho quente e contraria o ADR-0031 |
| Confiar em `types` para extrair o payload | ADR-0045: narrowing incompleto ⇒ miscompile silencioso |
| `var x: Int;` representado como opcional interno | exige repensar toda variável não inicializada; L6 |
| Tratar `T?` como `Any` | perde desboxamento e antecipa L6 |

## Como verificar

- `tests/corpus_manifest.py`: `variables.lox` promovido; casos novos de `Int?`, `Float?`,
  `Bool?`, função com `T?`, closure capturando `T?`, `??`, truthiness e unwrap narrowed.
- `tests/test_backend.py`: diferencial de stdout/stderr/exit code para os casos acima,
  inclusive `print` de `nil` e `b + 1` dentro de `if (b != nil)`.
- `tests/cases/defaults_as_value.lox` continua 65; `var x: Int;` ganha caso `PENDING`
  documentado.
- `make check` verde e `make bench` sem regressão >1.35x.

## Critérios para revisitar

- Se a checagem dupla de tag doer no L6, criar uma análise de refinamento confiável
  (CFG/aliasing) e remover os checks onde houver prova.
- Quando o L5 introduzir referências nulas, reutilizar `_coerce` e a representação de
  ponteiro nulo; não criar um segundo modelo de opcional.
- Se `var x: Int;` virar caso real no corpus, planejar a caixa `LoxValue` do L6.
