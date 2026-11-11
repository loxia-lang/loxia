# IDEIAS — caderno de design (parking lot)

Ideias ainda **não decididas**, com os argumentos dos dois lados, para pensar depois sem
perder o raciocínio. Diferente do `TODO.md` (o que fazer) e do `TIPOS.md` (contrato de
tipos): aqui é o **rascunho de decisões de linguagem**.

## Como usar

Cada entrada tem um id (`I-n`) e um status:

| Status | Significado |
| --- | --- |
| `ideia` | capturada, sem análise — só não quero esquecer |
| `em avaliação` | já tem opções e argumentos; falta decidir |
| `decidida` | virou decisão em `TODO.md` §11 (e `D-n` no `TIPOS.md`, se for de tipo) |
| `rejeitada` | descartada por ora, com o porquê registrado; os gatilhos dizem quando reabrir |

Formato: **pergunta → opções → argumentos → impacto técnico → recomendação provisória →
gatilhos para revisitar**.

> Regra: nada daqui é implementado antes de fechar a decisão no `TODO.md` §11. Quando
> decidir, mova o resumo para lá e marque a entrada como `decidida` (mantendo os
> argumentos como histórico).

---

## I-1 — Declaração de variáveis: `val` vs `var` e mutabilidade

**Status:** `decidida` — `val` imutável + `var` mutável; ver
[ADR-0005](docs/adr/0005-val-var-imutabilidade.md). O texto abaixo fica como histórico.

[TEXTO OMITIDO, SE UM DIA PRECISAR, OLHAR NO COMMIT PASSADO]
---

## I-2 — Pipeline: passar o valor da esquerda para a direita (`|>` / `:>`)

**Status:** `rejeitada` — **não haverá operador de pipeline** por enquanto (decisão de
2026-11-11). O texto abaixo fica como histórico: os argumentos continuam válidos e os
gatilhos dizem quando vale reabrir. Resumo registrado no [`TODO.md`](TODO.md) §11 (item 14)
e §1.4.

### Por que rejeitada (por enquanto)

- **Superfície demais para o ganho.** É um token, um nível de precedência e um conjunto de
  interações (com `;` opcional, com `and`/`or`, com o RHS) a aprender, documentar e testar.
- **Acopla decisões ainda abertas.** O exemplo canônico `foo() :> print()` só funciona com
  `print` como função ([`TODO.md`](TODO.md) §11 item 6) e a posição do argumento vira
  contrato da stdlib antes de a stdlib existir.
- **Convenção invisível.** Quem lê `x |> soma(1)` precisa saber onde o valor entra; errar
  cedo é caro porque muda toda API.
- **Redundante com o caminho OO.** `x.print()` / UFCS cobre boa parte dos casos sem
  operador novo (a alternativa segue viva em I-3), e o `TODO.md` §1 não tem caso de uso
  urgente antes de `List` e da stdlib.
- **Não é agora.** O código atual e os testes não sofrem com aninhamento; sem dor real, o
  custo de manutenção vem inteiro.

O que fica de pé: a regra "sujeito primeiro" para a stdlib e a análise do trade-off
abaixo, para o caso de reabertura. As perguntas abertas ficam sem resposta enquanto a
rejeição valer.

[TEXTO OMITIDO, SE UM DIA PRECISAR, OLHAR NO COMMIT PASSADO]

### Gatilhos para revisitar (caso a rejeição seja reaberta)

- dor real de aninhamento: o código passar a acumular `val passo1 = ...` (sinal de que
  pipe ajudaria);
- ao desenhar a stdlib (a ordem dos argumentos vira contrato);
- se UFCS/extension functions forem adotadas, pipe fica ainda mais redundante — sinal
  para manter rejeitado;
- ao definir a regra de `;` opcional (a interação com newline precisa estar pronta).

[TEXTO OMITIDO, SE UM DIA PRECISAR, OLHAR NO COMMIT PASSADO]

## I-3 — Funções soltas vs métodos: por que Python tem `len`, `print`, `int()`?

**Status:** `em avaliação`
**Decidir até:** ao desenhar a biblioteca padrão (depois do cap. 10). Com I-2 rejeitada, a
escolha fica entre **builtins puros** (canto 3 do triângulo) e **métodos/UFCS** (canto 2).

### A pergunta

1. Por que Python tem tantas funções soltas (`print`, `len`, `range`, `int`, `float`,
   `bool`, `dict`, `list`)?
2. Esse estilo é mais elegante/clean/moderno que "tudo é método"?
3. Para a nossa linguagem: builtins globais, métodos, funções namespaced ou extensões?

### Por que Python faz isso (as razões reais)

**1. Razão histórica.** O FAQ do CPython diz, na versão antiga: *"The major reason is
history. Functions were used for those operations that were generic for a group of types
and which were intended to work even for objects that didn't have methods at all (e.g.
tuples)"*. Ou seja: funções para operações **genéricas entre tipos**, inclusive tipos sem
métodos; e convenientes para `map()`/`zip()`.

**2. A justificativa do Guido** (hoje é a resposta oficial do FAQ), em duas partes:

> (a) For some operations, prefix notation just reads better than postfix — prefix (and
> infix!) operations have a long tradition in mathematics...
>
> (b) When I read code that says `len(x)` I *know* that it is asking for the length of
> something. This tells me two things: the result is an integer, and the argument is some
> kind of container. To the contrary, when I read `x.len()`, I have to already know that
> `x` is some kind of container implementing an interface or inheriting from a class that
> has a standard `len()`. Witness the confusion we occasionally have when a class that is
> not implementing a mapping has a `get()` or `keys()` method, or something that isn't a
> file has a `write()` method.
>
> — Guido van Rossum, [python-3000, 2006](https://mail.python.org/pipermail/python-3000/2006-November/004643.html)

O segundo ponto é o mais interessante: `len(x)` **documenta o contrato na leitura**, sem
depender do tipo de `x`. `x.len()` exige que você já saiba o que `x` é — e permite que
qualquer classe invente um `.get()` com semântica diferente.

**3. Protocolos (dunders).** `len(x)` chama `x.__len__()`; `str(x)` chama `x.__str__()`;
`iter(x)` chama `x.__iter__()`. O builtin é a **porta pública** do protocolo, e o dunder é
o *hook* de implementação. Vantagens: nomes não colidem entre tipos, duck typing funciona
sem herança, e `len`/`iter`/`next`/`str`/`hash`/`bool` espelham operadores da linguagem
(`if x`, `for x in xs`, `f"{x}"`, `x in d`).

**4. Implementação em C.** Adicionar `len()` a cada tipo C é mais código que uma função
genérica que despacha por slot; e o builtin é rápido (C-level).

**5. Tipos são callables.** `int`, `float`, `bool`, `list`, `dict` são **classes**, e
chamar uma classe constrói/converte. Então "cast" não precisa de sintaxe própria:
`int(x)` é o construtor de `int`. Uniforme e elegante — mas sobrecarrega o significado:
`int("42")` faz parse, `int(3.9)` trunca, `int()` devolve 0.

**6. `print` virou função no Python 3** porque um statement não consegue expressar
`sep`, `end`, `file=` nem compor (`map(print, xs)`). Quando a operação precisa de
flexibilidade, função ganha.

**7. Escopo global sem import** é ergonomia de script; o preço é poluir o namespace
(~150 builtins) e permitir shadowing acidental (`list = [1, 2]`).

### O que as outras linguagens fazem

| Linguagem | Onde ficam as operações | Exemplo |
| --- | --- | --- |
| Python | builtins globais + dunders + métodos | `len(x)`, `x.upper()`, `int(x)` |
| Ruby | métodos de `Kernel` (privados em todo objeto) | `puts`, `gets`, `raise` |
| Smalltalk | mensagens (tudo método) | `x printOn: t` |
| Java | métodos em `Object`/interfaces | `x.toString()`, `x.hashCode()` |
| C# | métodos + **extension methods** + LINQ | `xs.Where(f).ToList()`, `x.Foo()` |
| Kotlin | funções top-level + **extension functions** | `println(x)`, `x.isBlank()` |
| Swift | métodos + protocolos/extensões | `xs.map(f)` |
| Rust | traits (métodos) + funções em módulos | `xs.len()`, `std::mem::swap()` |
| Go | builtins para o irredutível + pacotes | `len(x)`, `slices.Sort(xs)` |
| JavaScript | globais + estáticos + protótipos | `parseInt(x)`, `Object.keys(o)`, `xs.map(f)` |
| Elixir | funções de `Kernel` importadas + pipe | `length(x)`, `x |> f()` |
| Haskell/F# | funções livres + composição/pipe | `f $ g x`, `x |> f` |

Padrão: **linguagens funcionais/dados** preferem funções livres + composição;
**linguagens OO/tipadas** preferem métodos + extensões. Python é um híbrido histórico
(procedural que ganhou classes), não uma escolha "moderna" deliberada.

### Elegante, clean, moderno? Análise

**Onde funções soltas ganham:**

1. **Problema da expressão**: dá para adicionar operação nova a tipos existentes sem
   tocar nos tipos (`len`, `map`, `filter` funcionam em qualquer coisa que implemente o
   protocolo). Com métodos, a operação precisa existir na classe.
2. **Tipos ficam pequenos**: protocolo mínimo em vez de dezenas de métodos em `Object`.
3. **Operações multi-tipo não pertencem a ninguém**: `min(a, b)`, `zip(xs, ys)`,
   `abs(x)` não são "método de" um dos operandos.
4. **Composição com pipe** (Elixir/F#): `x |> trim() |> split(",")`.
5. **Contrato visível na leitura** (argumento do Guido).

**Onde funções soltas perdem:**

1. **Descoberta**: autocomplete de `x.` não mostra `len`; o editor precisa tratar
   builtins à parte. Em linguagem tipada, método dá completude precisa.
2. **Namespace global**: ~150 nomes em Python; shadowing acidental é footgun.
3. **Sobrecarga semântica**: `int()` é parse + conversão + default; difícil de tipar.
4. **Tipagem estática**: `len(x)` exige um trait/protocolo genérico (`Sized`); sem isso,
   vira `Any -> Int` e perde checagem.
5. **Colisão com o usuário**: `list`, `str`, `id`, `type` como nomes de variável.

**Onde métodos ganham:** descoberta, namespace, dispatch estático (vtable/trait),
encadeamento natural (`xs.map(f).filter(g)`) e nada de função órfã.

**Onde métodos perdem:** primitivos precisam de métodos (`5.toString()`), operações
multi-tipo não cabem, estender tipo de terceiro exige extension methods/UFCS, e `nil`
quebra (`x.len()` explode; `len(x)` pode validar).

**Veredito:** o estilo Python é **coerente**, não "mais moderno". Os pontos fortes são
uniformidade de protocolo e tipos pequenos; os fracos são descoberta, namespace e a
composição. O mainstream tipado foi para **métodos + extensões** justamente para juntar
descoberta e abertura.

### O triângulo da ergonomia (conecta com I-2)

Só se escolhem **dois** destes três:

1. **funções livres + pipe** → composição linda (Elixir, F#);
2. **métodos/UFCS** → encadeamento lindo sem operador novo (Kotlin, C#, Rust);
3. **funções livres sem pipe** → aninhamento feio (`f(g(h(x)))`) — o canto do Python/JS.

É por isso que Python precisa de `functools`, `map/filter` viram `list(map(...))` e o
pessoal inventa `then`/method chaining. Se adotarmos pipe (I-2), a stdlib de funções
livres fica ótima; se adotarmos UFCS, pipe vira opcional. **Como I-2 está rejeitada**, o
primeiro canto sai do jogo por enquanto: ou aceitamos o aninhamento (3), ou vamos de
métodos/UFCS (2).

### Recomendação para a nossa linguagem

Híbrido explícito, com regra de bolso para decidir onde cada operação mora:

| Caso | Onde mora | Exemplo |
| --- | --- | --- |
| Protocolo/operador genérico | **builtin global** (poucos) | `len(x)`, `str(x)`, `println(x)` |
| Ação específica de um tipo | **método** | `lista.push(x)`, `texto.split(",")` |
| Construção/conversão | **construtor namespaced** | `Int.parse("42") -> Option`, `List.of(...)` |
| Combina dois tipos / composição | **função livre** | `min(a, b)`, `sum(xs)`, `map(xs, f)` |
| Sintaxe de método em função de usuário | **extensão** (P3) | `x.minhaExtensao()` |

Concretamente:

1. Builtins globais **mínimos**: `len`, `str`, `print`/`println`, `iter`/`next` (se
   houver `for-in`). Nada de `int()`/`float()` sobrecarregados.
2. Conversão **com nome e tipo**: `Int.parse("42")` devolve `Option[Int]`/`Result`;
   `x as Int` para cast explícito. Evita o `int()` de três significados.
3. `str` e `repr` separados? (Python acertou em ter os dois: usuário vs debug — decidir.)
4. Reservar builtins: redefinir `len` é erro (ou warning), não shadowing silencioso.
5. Se a stdlib crescer, mover para módulos (`std.io.println`) em vez de encher o global.
6. Adotar **extensões** (P3) para dar `x.metodo()` a funções — o melhor dos dois mundos.

Regra mental: *"depende de um tipo só e é ação dele → método; vale para vários tipos ou
combina dois → função livre; converte/constrói → construtor namespaced."*

### Impacto técnico

- **Checker**: `len` precisa de trait `Sized` (ou aceita `Any`); métodos precisam de
  tabela de tipos. Builtin com protocolo é o caminho mais barato para começar.
- **LLVM**: método = vtable/indireção; função livre = chamada direta (mais fácil de
  inlinar); pipe = zero-cost (desugar).
- **Stdlib**: cada operação precisa de uma casa; decidir cedo evita mover API depois.
- **Compatibilidade**: builtins globais são promessa eterna; namespace é mais fácil de
  evoluir.

### Gatilhos para revisitar

- ao desenhar a stdlib (depois do cap. 10);
- ao decidir builtins vs métodos/UFCS (I-2 rejeitada: resta escolher onde as operações
  moram);
- quando o type checker começar (protocolo `Sized`, generics);
- se o global começar a inchar (>30 builtins é sinal de alerta).

### Perguntas abertas

- [ ] `len` como função ou `.length`/`.tamanho` como método?
- [ ] `str` e `repr` separados? (debug vs usuário)
- [ ] conversões: `Int.parse` + `as Int`, ou funções `to_int`?
- [ ] builtins no escopo global ou em `std.*` importado por padrão?
- [ ] shadowing de builtin: proibir, permitir com warning, ou ignorar?
- [ ] métodos em primitivos (`5.toString()`)? Se sim, boxing?
- [ ] extension functions entram em qual fase? (P3)

### Referências

- FAQ do CPython — *"Why does Python use methods for some functionality but functions for
  other?"*:
  <https://docs.python.org/3/faq/design.html#why-does-python-use-methods-for-some-functionality-e-g-list-index-but-functions-for-other-e-g-len-list>
- Guido van Rossum, python-3000 (2006):
  <https://mail.python.org/pipermail/python-3000/2006-November/004643.html>
- Modelo de dados (protocolos `__len__`, `__iter__`, `__str__`):
  <https://docs.python.org/3/reference/datamodel.html>
- Ruby `Kernel` (funções como métodos privados):
  <https://docs.ruby-lang.org/en/master/Kernel.html>
- Kotlin extension functions: <https://kotlinlang.org/docs/extensions.html>
- C# extension methods: <https://learn.microsoft.com/dotnet/csharp/programming-guide/classes-and-structs/extension-methods>
- Go `len` embutido: <https://go.dev/ref/spec#Length_and_capacity>
- *The Expression Problem* (Wadler): <https://homepages.inf.ed.ac.uk/wadler/papers/expression/expression.txt>

---

## I-4 — Linguagem "agent-friendly": contratos + erros estruturados determinísticos

**Status:** `em avaliação`
**Decidir até:** contratos depois do cap. 10 (funções) e antes do codegen; formato JSON
junto com o redesign de diagnósticos (`TODO.md` §3.1).

### A pergunta

1. Design by Contract: `requires` / `ensures` / `invariant` na linguagem? Onde ficam?
2. Contratos são opcionais? Em que sentido (declarar, checar, custo)?
3. Erros em JSON estruturado para agentes, com resolução **determinística**, mantendo um
   stack trace humano tradicional.

### Parte A — Contratos (DbC)

#### Terminologia (importante)

O que foi descrito como "invariantes antes do bloco de código de uma função" é, na
literatura, uma **pré-condição**. Os três conceitos:

| Conceito | Onde | Verifica |
| --- | --- | --- |
| **Pré-condição** (`requires`) | antes do corpo | o que o chamador deve garantir |
| **Pós-condição** (`ensures`) | depois do corpo | o que a função garante, dado que a pré valeu |
| **Invariante de classe** (`invariant`) | na classe | vale na entrada e saída de todo método público |
| **Invariante de laço** | no `while`/`for` | vale antes/depois de cada iteração (mais difícil; P3) |

Usar "invariante" para "checagem no topo da função" confunde com invariante de classe e
de laço. Recomendo os três nomes distintos desde o início.

#### Sintaxe proposta (Eiffel/Dafny-like, entre assinatura e corpo)

```lox
fn dividir(a: Int, b: Int) -> Int
  requires b != 0
  requires a >= 0
  ensures result * b <= a
{
  a / b
}

class Conta {
  var saldo: Int
  invariant saldo >= 0

  fn sacar(valor: Int)
    requires valor > 0
    requires valor <= saldo
    ensures saldo == old(saldo) - valor
  {
    saldo = saldo - valor
  }
}
```

Regras:
- `requires`/`ensures`/`invariant` são **cláusulas opcionais** entre a assinatura e `{`.
- No `ensures`, `result` é o valor de retorno e `old(expr)` é o valor da expressão na
  entrada (snapshot **raso**; documentar que `old(lista)` não congela o conteúdo).
- `invariant` de classe é checado na entrada e na saída de métodos públicos (não em
  métodos privados, para não pagar duas vezes).
- Expressões de contrato são **puras**: sem I/O, sem atribuição, sem `throw`. O checker
  deve impor isso (ou restringir a um subconjunto: comparações, aritmética, `len`,
  chamadas a funções marcadas `pure`).
- Herança (cap. 13): pré-condições podem ser **enfraquecidas**, pós-condições
  **fortalecidas** (Liskov); invariantes são herdados e checados junto.

#### Opcional? Sim, em três eixos — mas com default esperto

| Eixo | Opções | Recomendação |
| --- | --- | --- |
| **Declarar** | com/sem cláusulas | opcional por função (zero contrato = zero custo) |
| **Checar** | `off` / `check` / `warn` | `check` no interpretador/dev; `off` no nativo release, ligável com `--contracts=check` |
| **Onde** | runtime / estático | runtime por padrão; o checker pode provar alguns casos triviais e evitar a checagem |

- `--contracts=off`: cláusulas são **parseadas e tipadas** (não podem ter erro de tipo),
  mas não executadas. Documentar que "off" é otimização, não permissão para código
  quebrado.
- `--contracts=warn`: só para migração — loga a violação e continua. Perigoso (segue com
  estado inválido); nunca default.
- Violação é **falha fatal** (como `assert`), não `throw` recuperável: contrato violado é
  bug, e `try/catch` em volta mascararia. No REPL, reporta e mantém a sessão viva.
- Custo: pós-condição com `old(...)` pode alocar snapshot; contrato com `sorted(xs)` é
  O(n log n) — documentar a complexidade e permitir `off`.

#### Contratos como testes (bônus valioso)

Pré e pós-condições são **oráculos de teste de graça**: um gerador (property-based testing,
futuro `hypothesis`) pode produzir entradas que satisfazem `requires` e verificar
`ensures`. Isso transforma contrato em teste sem escrever teste. É o argumento mais forte
a favor de DbC na linguagem, e combina com o fuzzing já previsto no `TODO.md` §7.

#### Impacto técnico

- **Parser**: três cláusulas novas, só entre assinatura e corpo; sem ambiguidade.
- **Resolver**: contratos enxergam parâmetros e (em `ensures`) `result`/`old`; `old` exige
  guardar snapshot na entrada.
- **Checker**: pureza, tipos, e `result` só em `ensures`.
- **Interpretador**: avaliar antes/depois; erro estruturado em vez de `LoxRuntimeError`
  genérico.
- **LLVM**: cada cláusula vira `icmp` + branch para o runtime de falha; `--contracts=off`
  remove tudo. Cuidado: **não** transformar contrato em `llvm.assume` sem checagem — se a
  pré-condição for violada, o comportamento é UB em vez de erro. Primeiro checar, depois
  (talvez) usar como hint.
- **Testes**: golden de contrato (violação com `kind`, `clause`, `bindings`), e teste de
  que `off` não altera o resultado.

### Parte B — Erros estruturados em JSON

#### Princípio

Um único **modelo de diagnóstico** interno; dois renderizadores: **humano** (caret +
cores + stack trace) e **JSON** (máquina). Nunca gerar a mensagem duas vezes.

#### Esquema proposto (v1)

```json
{
  "schema_version": "1.0",
  "command": "check",
  "success": false,
  "summary": { "errors": 1, "warnings": 0 },
  "diagnostics": [
    {
      "code": "E3001",
      "kind": "type_mismatch",
      "severity": "error",
      "phase": "typecheck",
      "message": "expected Float, found String",
      "span": {
        "file": "src/main.lox",
        "start": { "line": 3, "column": 9, "offset": 41 },
        "end":   { "line": 3, "column": 14, "offset": 46 }
      },
      "labels": [
        { "span": { "file": "src/main.lox", "start": { "line": 3, "column": 9 }, "end": { "line": 3, "column": 14 } },
          "message": "encontrado String" }
      ],
      "notes": ["o valor vem de `pessoa.nome` (linha 2)"],
      "help": "use `as Float` para converter explicitamente",
      "docs": "https://lox.dev/errors/E3001",
      "fixes": [
        {
          "applicability": "machine-applicable",
          "edits": [
            { "file": "src/main.lox",
              "span": { "start": { "offset": 41 }, "end": { "offset": 46 } },
              "replacement": "(pessoa.nome as Float)" }
          ]
        }
      ]
    }
  ]
}
```

Campos-chave:
- `code` **estável** (`E3xxx` tipo, `E1xxx` parser, `C1xxx` contrato, `R1xxx` runtime) e
  nunca reutilizado; `docs` aponta para o catálogo.
- `span` com **linha, coluna e offset em bytes** (offset é o que o editor/agente usa para
  editar sem ambiguidade; linha/coluna é o que o humano lê).
- `fixes[]` com `applicability` (`machine-applicable`, `maybe-incorrect`, `manual`) e
  `edits[]` com substituição por span — é o que permite o agente corrigir sem adivinhar.
- `kind` separa categorias sem quebrar `code`.

Violação de contrato usa o mesmo envelope:

```json
{
  "code": "C1002",
  "kind": "contract_violation",
  "phase": "runtime",
  "message": "precondition failed: b != 0",
  "function": "dividir",
  "clause": "requires",
  "span": { "file": "src/main.lox", "start": { "line": 2, "column": 12 }, "end": { "line": 2, "column": 18 } },
  "bindings": { "a": "10", "b": "0" },
  "trace": [ { "function": "main", "file": "src/main.lox", "line": 9 } ]
}
```

`bindings` mostra os valores das variáveis citadas na cláusula — o equivalente
estruturado do "mostre os argumentos no panic".

#### Determinismo (o que faz a resolução ser repetível)

1. **Ordenação fixa**: por `(file, start.offset, code)`; nunca pela ordem de um `dict`
   ou de um `set` (foi exatamente a classe de bug do `<object at 0x...>`).
2. **Sem dados voláteis**: nada de timestamps, PID, endereço de memória, caminho absoluto,
   locale ou ordem de `os.listdir`. Caminhos **relativos à raiz do projeto**.
3. **Formatação numérica canônica**: uma única `stringify` (ver
   [ADR-0006](docs/adr/0006-int-float-separados.md)) para
   mensagens e `bindings`; float sempre com representação round-trip.
4. **Dedup e cascata**: um erro raiz gera um diagnóstico primário; derivados viram
   `notes`/`related`, não erros novos. Limite `--max-errors`.
5. **Códigos e schema versionados**: `schema_version` no envelope; código nunca muda de
   significado. Mudança incompatível = nova major do schema.
6. **Saída separada**: em `run`, o stdout é do **programa**; diagnósticos vão para o
   **stderr** (JSON único ou NDJSON). Em `check`, o JSON vai para o stdout.
7. **Mesmo input → mesmo output**: teste de determinismo roda duas vezes e compara bytes
   (exceto nada — deve ser idêntico).

#### Protocolo de reparo determinístico (para agentes)

```
1. lox check --json            → diagnostics[]
2. selecionar fixes com applicability == "machine-applicable"
3. descartar edits sobrepostos (aplicar só os disjuntos; reportar os demais)
4. aplicar edições atomicamente (ou --fix --dry-run para só receber o diff)
5. reexecutar
6. progresso obrigatório: erros diminuíram OU conjunto de codes mudou
7. parar após N iterações (ex.: 10) ou quando success == true
8. se não houver fix: usar help/docs/code — nunca "adivinhar" edição
```

Comandos que tornam isso possível:
- `lox check --json` / `lox build --json` / `lox run --json` (diagnósticos);
- `lox check --fix --dry-run --json` (devolve `fixes[]` sem escrever);
- `lox explain E3001 --json` (entrada do catálogo, com exemplo e contraexemplo);
- `lox capabilities --json` (versão, schema, códigos suportados, exit codes).

#### Lado humano

- `--error-format=human|short|json|json-lines` (default `human` em TTY).
- O renderizador humano usa os mesmos `Diagnostic`s: caret, cores (`NO_COLOR`), notas e
  **stack trace** com frames (`at dividir (linha 2) ← main (linha 9)`).
- `--json` não pode degradar a experiência humana: o humano vê o mesmo erro bonito, só que
  em outro formato quando pedir.

### Parte C — Checklist "agent-friendly" (além de erros)

- [ ] `--json` em todos os comandos de inspeção (`check`, `ast`, `types`, `fmt --check`).
- [ ] **Nunca** prompt interativo; `--yes`/`--non-interactive` onde houver risco.
- [ ] Exit codes estáveis e documentados (65 sintaxe, 70 runtime, 66 arquivo; contrato
      pode virar 71 no futuro, mas `kind` já distingue).
- [ ] `--color=auto|always|never` e `NO_COLOR`; saída sem ANSI quando não-TTY.
- [ ] `--no-progress`; progresso só em stderr.
- [ ] Sem rede, sem telemetria, sem escrita fora do projeto.
- [ ] `--timeout` para execução (agente não pode travar em loop infinito).
- [ ] Catálogo de erros em JSON versionado no repo (`docs/erros/`), gerado dos códigos.
- [ ] Formatter idempotente e determinístico (`fmt` duas vezes = igual).
- [ ] Builds reproduzíveis (sem caminho absoluto no binário/objeto).
- [ ] `llms.txt`/`docs/agents.md`? (documentação pensada para agente, curta e factual)

### Argumentos a favor

1. **Contrato é documentação executável**: a intenção fica no código e é verificada, não
   em comentário que apodrece.
2. **Erro cedo e local**: a violação aponta a cláusula e os valores, não um stack trace
   genérico três camadas depois.
3. **Testes de graça**: pré/pós viram oráculo para property-based testing e fuzzing.
4. **Agente confiável**: JSON com `code`/`span`/`fixes` reduz alucinação; o protocolo de
   reparo é auditável e repetível.
5. **Humano não perde nada**: mesmo diagnóstico, renderizado bonito; JSON é opcional.
6. **Determinismo ajuda todo mundo**: cache de CI, diff de diagnósticos, testes de
   regressão de mensagem.
7. **Barato de começar**: contratos são só cláusulas opcionais; JSON é um renderizador a
   mais sobre o reporter que já existe.

### Argumentos contra

1. **Custo de execução**: pós-condições com `old`/`len`/ordenação podem dominar o tempo;
   `off` no release é obrigatório, mas aí o contrato deixa de valer em produção.
2. **Falsa segurança**: contrato não é verificação formal; cobre o que foi escrito.
   DbC não substitui type checker nem testes.
3. **Complexidade de linguagem**: mais três cláusulas, `old`, `result`, pureza, herança —
   é bastante superfície para uma linguagem em construção.
4. **JSON é contrato eterno**: schema e códigos viram API pública; errar cedo custa caro.
5. **Risco de "agent-only"**: features que só agente usa tendem a apodrecer; por isso o
   humano tem que consumir o mesmo modelo.
6. **Determinismo dá trabalho**: caminhos, floats, ordem de diagnósticos e dedup exigem
   disciplina em todo lugar (não só no reporter).
7. **Contratos em LLVM**: fácil de implementar, fácil de errar (`assume` = UB).

### Recomendação provisória

- **Contratos: sim, opcionais por declaração**, com `requires`/`ensures`/`invariant`,
  checagem **ligada por padrão no interpretador** e **desligável no nativo**
  (`--contracts=off|check|warn`). Violação = erro fatal estruturado (`C1xxx`), não
  exceção capturável.
- **Erros: um modelo, dois renderizadores**, JSON v1 com `code`/`span`/`fixes`, ordenação
  determinística e `--error-format`. Implementar **junto** com o redesign do §3.1 (não
  depois), senão o formato nasce torto.
- **Protocolo de reparo** documentado (`check --json` → aplicar `fixes` → reexecutar →
  progresso), com `--fix --dry-run` e `explain`.
- **Ordem prática**: JSON/determinismo primeiro (serve ao humano e ao agente, e é
  pré-requisito do LSP); contratos depois do cap. 10, quando há funções para anotar.

### Riscos e anti-metas

- Não tratar contrato como fronteira de segurança: com `off`, ele não existe.
- Não permitir efeito colateral em contrato (nem `print` de debug).
- Não emitir JSON com endereço/timestamp/ordem instável — quebra cache e confiança.
- Não criar um segundo modelo de erro para agente; o humano e o agente leem o mesmo.
- Não usar `llvm.assume` em contrato antes de ter checagem (UB silencioso).
- Não versionar schema sem `schema_version` e sem teste de compatibilidade.

### Gatilhos para revisitar

- ao implementar o redesign de diagnósticos (`TODO.md` §3.1);
- ao terminar funções (cap. 10) — primeiro momento para `requires`/`ensures`;
- ao entrar em classes (cap. 12) — `invariant`;
- ao começar o codegen (contratos em LLVM);
- quando houver `lox check --json` (aí medir se o agente realmente resolve com `fixes`).

### Perguntas abertas

- [ ] `requires`/`ensures` ou `pre`/`post` (mais curto)? E `old`/`result`?
- [ ] Contrato no topo do corpo (`invariant x > 0`) em vez de cláusula? (não recomendo)
- [ ] `off` remove a checagem **e** a avaliação das expressões? (sim, senão não otimiza)
- [ ] Violação de contrato: exit 70 com `kind` ou exit 71 dedicado?
- [ ] `fixes` automáticos: só para sintaxe/typo, ou também semânticos?
- [ ] JSON em stderr (run) vs stdout (check) — confirmar contrato de CLI.
- [ ] `schema_version` por major/minor? Onde fica o catálogo de códigos?
- [ ] Contratos entram no AST público (`--ast --json`)? (sim, para tooling)
- [ ] Invariante de laço entra em qual fase? (P3)

### Referências

- Design by Contract (Eiffel): <https://www.eiffel.com/values/design-by-contract/>
- C++26 contracts: <https://en.cppreference.com/w/cpp/language/contracts>
- Rust contracts (RFC/discussão): <https://github.com/rust-lang/rfcs/pull/2850>
- Dafny (requires/ensures/invariant verificados): <https://dafny.org/>
- SPARK/Ada (contratos + análise estática): <https://www.adacore.com/sparkpro>
- Python `icontract`: <https://github.com/Parquery/icontract> · `deal`:
  <https://deal.readthedocs.io/>
- JSON Schema: <https://json-schema.org/>
- SARIF (formato de diagnóstico para CI): <https://sarifweb.azurewebsites.net/>
- Diagnósticos JSON do rustc:
  <https://rustc-dev-guide.rust-lang.org/diagnostics.html#json-output>
- LSP `Diagnostic`: <https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#diagnostic>
- Property-based testing: <https://hypothesis.readthedocs.io/>

---

## I-5 — Parâmetros opcionais/default e mutabilidade de campos de classe

**Status:** `em avaliação`
**Origem:** desdobramento de I-1/ADR-0005 — campos de classe foram adiados; a ideia é
aproximar a assinatura de funções do estilo Python (`a: Int`, `b: Int | Nil = nil`) e
definir como `val`/`var` valem dentro de objetos.

### A pergunta

1. Funções podem ter parâmetros **obrigatórios e opcionais com default**, como Python?
2. Defaults valem para **todas** as funções, métodos e `init`?
3. Quando o default é avaliado: na declaração ou na chamada?
4. Como campos de classe ganham `val`/`var`? O que pode ser atribuído no `init`?
5. Existe "classe imutável" ou isso é só "todos os campos são `val`"?

### Proposta de sintaxe (alvo, com tipos futuros)

```lox
fn conectar(host: String, porta: Int = 80, timeout: Int | Nil = nil) -> Bool {
  // ...
}

class Pessoa {
  val nome: String
  var idade: Int = 0

  init(nome: String, idade: Int = 0) {
    this.nome = nome
    this.idade = idade
  }

  fn aniversario() {
    this.idade = this.idade + 1   // ok: campo var
  }
}

var p = Pessoa("Ana")            // idade = 0
var q = Pessoa("Bia", 30)        // idade = 30
```

Ideias:
- parâmetros obrigatórios vêm **antes** dos opcionais (como Python/Kotlin);
- um parâmetro opcional carrega um valor default que também participa da checagem de tipo;
- `T | Nil = nil` é o jeito explícito de "opcional que pode ser nulo";
- a **aridade** de uma função deixa de ser um número e vira um intervalo
  (`[obrigatórios, total]`), o que afeta mensagens de erro, classes e LLVM.

### Defaults: quando avaliar?

| Estratégia | Semântica | Prós | Contras |
| --- | --- | --- | --- |
| **Na chamada** (Kotlin) | o default é avaliado a cada chamada, no escopo do chamador | sem estado compartilhado; intuitivo | exige código de "preencher" no call site; LLVM gera mais IR |
| **Na declaração** (Python) | avaliado uma vez, no escopo da declaração | simples de implementar | armadilha clássica: default mutável compartilhado entre chamadas |
| **Só constante** | literal/`nil` apenas | trivial, determinístico, simples no codegen | menos expressivo (sem `list()` nem `agora()`) |

Recomendação provisória: **só constante** no começo (`nil`, literais, talvez `true/false`)
e evoluir para avaliação na chamada quando houver type checker. Evita copiar de graça o
problema de `def f(xs=[])` do Python.

### Impacto nos erros e na tipagem

- Mensagem de aridade vira algo como `Expected 1 to 3 arguments but got 4.`
  e, para chamada curta, `Expected at least 2 arguments but got 1.`
- O checker precisa preencher os tipos dos parâmetros omitidos a partir do default.
- Defaults em `init` definem a aridade da classe (hoje é a aridade exata do `init`).
- Parâmetros `var` com default (`fn f(var x = 0)`) devem ser permitidos ou não? (decidir)
- Defaults não podem referenciar parâmetros anteriores? (Python permite só no corpo;
  Kotlin permite defaults independentes). Recomendo **não** permitir dependência entre
  parâmetros no default na v1.

### Campos de classe: opções

**A) Continuar dinâmico (hoje).** Campos nascem no `init`/atribuição; todos mutáveis.
Simples, mas sem `val`, sem checagem e sem tipo.

**B) Campos declarados no corpo, com `val`/`var` (recomendado).**

```lox
class Pessoa {
  val nome: String
  var idade: Int = 0
}
```

- `val` campo: inicializado na declaração **ou** dentro de `init` (uma vez), e não pode
  ser atribuído depois que o `init` termina (checagem estática, como Kotlin).
- `var` campo: atribuível em qualquer método.
- Campo sem inicializador precisa ser atribuído no `init`; senão erro de compilação.
- Herança: campo `val` não pode ser reatribuído na subclasse; `var` pode (com as regras de
  visibilidade a definir).
- `this.campo = ...` passa a ser checado pelo resolver/checker (hoje é dinâmico).

**C) Estilo Kotlin: parâmetros do construtor viram campos.**

```lox
class Pessoa(val nome: String, var idade: Int = 0)
```

Muito conciso e resolve required/optional + campos de uma vez. Custo: muda a forma da
classe, mistura construtor com declaração e conflita com o `init` explícito do Lox; mais
difícil de casar com o modelo atual.

**D) Estilo dataclass do Python: anotações e defaults no corpo, `init` gerado.**
Ainda mais mágica; não combina com o `init` manual que já temos.

Recomendação provisória: **B** quando o type checker chegar — mantém `init` explícito,
torna a mutabilidade visível e mapeia bem para LLVM (campos com offset fixo). `val` de
campo só é atribuível dentro do `init` (uma vez), `var` em qualquer lugar. "Classe
imutável" seria apenas uma classe em que **todos** os campos são `val`; não precisa de
keyword nova.

### Impacto técnico

| Camada | O que muda |
| --- | --- |
| Parser | `parameter (":" Type)? ("=" expression)?` temporário até tipos; campos no corpo da classe |
| Resolver | saber se está dentro de `init` (para `val` field), rastrear campos por classe |
| Checker | defaults, aridade variável, tipos de campo, atribuição em `init` |
| Interpreter | preencher defaults; inicializar campos; checar `val` field em runtime (fallback) |
| LLVM | defaults viram código no call site; campos viram offsets/`getelementptr` |

### Perguntas abertas

- [ ] Defaults: constante, avaliação na chamada ou na declaração?
- [ ] Parâmetros opcionais podem ser `var`?
- [ ] Named arguments (chamar `f(porta = 8080)`)? (provável P3)
- [ ] `val` de campo: exigir inicialização na declaração ou permitir no `init` uma vez?
- [ ] Campo sem `val`/`var` explícito: erro, ou default `var` por compatibilidade?
- [ ] `val` field em classe herdada: proibir reatribuição em qualquer subclasse?
- [ ] Classes imutáveis precisam de sintaxe própria (`immutable class`) ou é só "todos
      os campos `val`"?
- [ ] Defaults afetam `super(...)`/`init` herdado? (aridade da subclasse)

### Referências

- Kotlin — default arguments e `val`/`var` em propriedades:
  <https://kotlinlang.org/docs/functions.html#default-arguments>
- Python — default arguments e a armadilha de mutáveis:
  <https://docs.python.org/3/tutorial/controlflow.html#default-argument-values>
- C# — optional/named arguments:
  <https://learn.microsoft.com/dotnet/csharp/programming-guide/classes-and-structs/named-and-optional-arguments>
- Swift — default parameter values:
  <https://docs.swift.org/swift-book/documentation/the-swift-programming-language/functions/>

### Complemento — `*args` e `**kwargs` (variádicos)

**Status:** `em avaliação` (não implementar agora)

Vale ter coleta de argumentos extras, no estilo Python?

```lox
// candidato 1: asteriscos
fn somar(*numeros) -> Int { /* numeros é List[Int] */ }
fn log(nivel: String, *partes) { /* ... */ }

// candidato 2: reticências (Lox2/Kotlin-ish, evita colidir com multiplicação)
fn somar(...numeros) -> Int { /* ... */ }
fn log(nivel: String, ...partes) { /* ... */ }
```

`**kwargs` só faz sentido se existir **argumento nomeado** na chamada
(`f(x = 1, y = 2)`), que é outra feature grande.

#### Como outras linguagens resolvem

| Linguagem | Extra posicionais | Extra nomeados |
| --- | --- | --- |
| Python | `*args` (tuple) | `**kwargs` (dict) |
| Kotlin | `vararg` | não (named args explícitos) |
| Go | `...T` | não |
| Java | `T...` | não |
| Rust | não tem varargs de usuário | não |
| JavaScript | `...args` (rest) | object/`arguments` |
| C | `...` (varargs não tipado) | — |

#### Viabilidade de `*args`

- **Runtime:** `LoxCallable.arity()` deixa de bastar. Seria preciso algo como
  `min_arity()` + `accepts(n)` ou uma `Signature`, e `call` recebendo a lista de extras.
  A mensagem de aridade vira "pelo menos N" (`Expected at least 2 arguments but got 1.`).
- **Parser/AST:** `Param` ganha um flag `variadic`; só um rest por função e sempre por
  último; a chamada **não** muda (os extras simplesmente são aceitos).
- **Semântica:** o binding do rest é `val` (a lista pode ser mutável, mas o nome não muda);
  defaults só antes do rest; `fn f(a = 1, ...xs)` é aceitável, `fn f(...xs, a)` não.
- **Tipos:** `...numeros: Int` vira `List[Int]`; a chamada aceita qualquer quantidade e o
  checker unifica todos os extras. No LLVM, empacotar os extras em array/lista alocada.
- **Custo:** médio. Útil para `print`/logging/FFI/decorators, mas muita coisa se resolve
  com uma lista explícita: `fn somar(ns: List[Int])` + `somar([1, 2, 3])`.
- **Veredito:** viável e provavelmente útil, mas depois de existirem `List`, o type checker
  e um caso de uso concreto (P2/P3).

#### Viabilidade de `**kwargs`

- **Depende de named arguments**, que é uma feature grande por si só: parser da chamada,
  ordem de avaliação, nomes desconhecidos, duplicados, interação com defaults e com
  `init`/herança.
- **Sem named args, `**kwargs` é sempre vazio** — não serve para nada.
- Com named args, `**kwargs` é o "resto dinâmico": vira `Map[String, Any]`, destrói a
  tipagem estática, complica mensagens e o codegen LLVM. Python usa porque é dinâmico;
  nós queremos tipos inferidos.
- **Alternativa tipada:** named args + defaults + objeto de configuração explícito
  (`fn conectar(cfg: Config)`), que é documentável, checável e fácil de compilar.
- **Custo alto, benefício baixo** para este projeto.
- **Veredito:** **não** no curto/médio prazo; provavelmente nunca. Se um dia, só com `Map`
  tipado e regras de conversão explícitas.

#### Named args ≠ `**kwargs` (esclarecimento)

**Argumento nomeado** é uma forma de **chamar**: o nome do parâmetro aparece no call site.

```lox
fn conectar(host: String, porta: Int = 80, tls: Bool = false) { ... }

conectar("exemplo.com", porta = 443, tls = true)
```

- os nomes são **declarados na assinatura** (conjunto fixo e conhecido);
- o compilador casa nome → posição, aplica defaults e checa tipos;
- nome desconhecido, duplicado ou obrigatório faltando = erro de compilação;
- no LLVM vira chamada posicional normal (custo zero).

**`**kwargs`** é um **parâmetro que captura nomes não declarados**:

```python
def config(**opcoes):      # opcoes é dict[str, Any]
    ...

config(cor="azul", tamanho=3)
```

- a função **não declara** `cor` nem `tamanho`; qualquer nome entra no dicionário;
- erros de digitação passam, os tipos se misturam e o checker só vê `Map[String, Any]`;
- no LLVM vira estrutura dinâmica (hash map), não offset fixo.

Resumindo: **named args são o mecanismo; `**kwargs` é a coleta aberta do que sobrar.**
Em Python, `f(a=1, b=2, c=3)` com `def f(a, b=0, **kw)` produz `a=1`, `b=2` e
`kw={"c": 3}` — os dois primeiros são argumentos nomeados casados com parâmetros; o
terceiro "cai" no `**kwargs` porque não foi declarado.

| Aspecto | Named args | `**kwargs` |
| --- | --- | --- |
| Onde os nomes existem | assinatura | call site (qualquer nome) |
| Checagem | compilação | runtime |
| Tipo de cada valor | declarado | `Map[String, Any]` |
| Typo no nome | erro | aceito silenciosamente |
| Autocomplete/IDE | sim | não |
| Defaults | por parâmetro | decididos pela função |
| LLVM | posicional, custo zero | hash map dinâmico |

**Na nossa linguagem:** chamadas são 100% posicionais hoje. Named args exigiriam resolver
uma ambiguidade real: `f(x = 1)` hoje é uma chamada cujo argumento é a **expressão de
atribuição** `x = 1`; com named args passaria a significar "passe `1` para o parâmetro
`x`". Seria preciso proibir atribuição solta como argumento (exigir `f((x = 1))`) ou
escolher outra sintaxe. É factível, mas é uma decisão de parser/checker, não só de açúcar.
`**kwargs` continua dependendo de `Map` tipado e de named args, e por isso não compensa.

#### Interações com o resto de I-5

- `*args` + defaults: defaults só antes do rest; chamada curta usa defaults, extras vão
  para o rest.
- `init` variádico: complica a aridade da classe e o `init` herdado; evitar no começo.
- Spread no call site (`f(...lista)`) é o espelho do rest e também exige token novo
  (`...`); não confundir declaração variádica com spread.
- `*args` e `**kwargs` não são `val`/`var`: são parâmetros especiais; o binding do rest
  deve ser imutável.

#### Perguntas abertas

- [ ] `*args` (Python) ou `...args` (Lox2/Kotlin)? `...` evita ambiguidade com `*` e
      combina com spread.
- [ ] o rest pode ser `var` (reatribuir a lista)? (recomendo não)
- [ ] permitir rest em `init`/métodos? Se sim, a aridade da classe vira "pelo menos N".
- [ ] defaults depois do rest? (recomendo proibir)
- [ ] `print`/`log` nativos viram variádicos ou continuam aceitando uma lista?
- [ ] named args vêm antes de `**kwargs`? (sim; `**kwargs` só depois)

---

## I-6 — Ranges e iteráveis: o que pode aparecer no `for x in`

**Status:** `decidida` — ver [ADR-0007](docs/adr/0007-ranges-e-iteracao.md) e
[`TIPOS.md`](TIPOS.md) §3.6. Implementado no tree-walk para `Range` e `String`; `List`/`Map`
entram quando existirem.

### A pergunta

1. Range é literal (`0..10`) ou função (`range(...)`)?
2. O que é iterável numa linguagem em que primitivos não são objetos?
3. Range é lista eager ou valor lazy? O laço é protocolo ou desaçúcar para C-style?

### Decisão

- **`a..b` half-open**, só `Int`, lazy e reutilizável; `range(a, b, step)` (3 argumentos)
  para passo/descendente. `..=` fica adiado.
- **`for x in` v1**: `Range` → `Int`; `String` → `String` de 1 code point. List/Map quando
  existirem (Map → chaves em ordem de inserção).
- **Variável do laço é `val` novo por iteração**; reatribuir é erro e closures capturam o
  valor daquela iteração.
- **Mutar a coleção durante a iteração** é proibido/indefinido na v1.
- `map`/`filter` serão **eager** (`List`) quando existirem; `contains` será função, não
  operador `in`.
- **Protocolo de usuário** (`Iterable[T]` estrutural, `next() -> T?`) só depois de
  `Option`/traits.

### Por que (resumo)

- Iteração é protocolo, não herança: primitivos podem ser iteráveis sem virarem classes.
- Builtin-only agora evita expor `Iterator`/`Option` cedo e não fecha a porta para classes.
- Range lazy evita alocar (`0..1_000_000_000`) e half-open evita off-by-one.
- Binding novo por iteração elimina o *late binding* de closure do Python.
- Ordem de inserção em Map preserva o determinismo do I-4.

### O que falta

- `List`/`Map` como fontes de iteração (os tipos ainda não existem).
- `..=` e ranges inclusivos.
- `Iterable` de usuário (depende de `Option` para o fim do iterator).
- `contains`, `sum`, `enumerate`, `zip` (stdlib/Tuple).

### Gatilhos para revisitar

- quando List/Map chegarem;
- quando `Option`/traits entrarem (protocolo de usuário);
- se `..=`/passo virarem necessidade real;
- se `map`/`filter` eager começarem a doer em memória.
