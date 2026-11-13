# ADR-0016 — API da stdlib: modelo híbrido, prelúdio mínimo e builtins reservados

- **Status:** accepted
- **Data:** 2026-11-11
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0015](0015-listas-tipadas.md), a discussão histórica de I-3 (git),
  [`TODO.md`](../../TODO.md) §11, [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/execution/prelude.py`](../../src/execution/prelude.py),
  [`src/execution/natives/str.py`](../../src/execution/natives/str.py),
  [`src/execution/natives/repr.py`](../../src/execution/natives/repr.py),
  [`src/semantics/checker.py`](../../src/semantics/checker.py), [`src/execution/interpreter.py`](../../src/execution/interpreter.py),
  [`tests/cases/str_repr.lox`](../../tests/cases/str_repr.lox),
  [`tests/cases/builtin_shadow_local.lox`](../../tests/cases/builtin_shadow_local.lox)

> **Atualização (ADR-0026, 2026-11-12):** `clock` saiu do prelúdio da 1.0. Onde este ADR
> o lista como builtin reservado, vale o [ADR-0026](0026-freeze-1.0.md): o prelúdio é
> `len`, `str`, `repr` e `range`.

## Contexto

A discussão histórica de I-3 compara **funções soltas** e **métodos** e conclui que o estilo
Python é coerente, mas não é a única escolha: linguagens tipadas foram para métodos +
extensões para ganhar descoberta sem perder abertura. Com o pipe rejeitado, sobravam
dois cantos: aninhamento de funções ou métodos/UFCS.

A implementação de `List[T]` ([ADR-0015](0015-listas-tipadas.md)) deu o primeiro caso real
e resolveu a pergunta mais importante daquela discussão:

- `len(xs)` é **função global** — funciona para `List`, `String` e, no futuro, `Map`, sem
  exigir método em primitivo;
- `xs.push(v)` / `xs.pop()` são **métodos** — são ações específicas de lista, um objeto de
  runtime (`LoxList`), não de um primitivo.

Isso validou o **modelo híbrido** e permitiu fechar as perguntas restantes: `str`/`repr`,
escopo dos builtins, shadowing, métodos em primitivos e fase das extensões. A API de
**conversões** ficou deliberadamente em aberto porque `as` também é candidato a alias de
import (estilo Python) e a sintaxe de cast precisa ser decidida com calma.

## Decisão

### 1. Modelo híbrido explícito

A stdlib segue uma regra de bolso, não "tudo é função" nem "tudo é método":

| Caso | Onde mora | Exemplos |
| --- | --- | --- |
| Protocolo/operador genérico | **builtin global** | `len(x)`, `str(x)`, `repr(x)`, `print`/`println` |
| Ação específica de um tipo | **método** | `xs.push(v)`, `xs.pop()`, `s.split(",")` (futuro) |
| Construção/conversão | **construtor namespaced** (alvo) | `Int.parse("42")`, `List.of(...)` (futuro) |
| Combina dois tipos / composição | **função livre** | `min(a, b)`, `sum(xs)`, `map(xs, f)` (futuro) |
| Usuário adiciona método a tipo existente | **extensão/UFCS** (P3) | `s.minhaExtensao()` (futuro) |

A regra mental: *depende de um tipo só e é ação dele → método; vale para vários tipos ou
combina dois → função livre; converte/constrói → construtor namespaced.*

### 2. Prelúdio global mínimo

O escopo global não é a casa da stdlib inteira. Ficam no prelúdio apenas as operações
irredutíveis ou usadas em todo programa:

- **hoje:** `clock`, `len`, `range`, `repr`, `str` (e `print` como statement);
- **futuro próximo:** `println` como função, se/quando `print` deixar de ser statement;
- **todo o resto:** em `std.*` quando o sistema de módulos existir (`std.math`, `std.io`,
  `std.conv`, ...).

Sinais de alerta: mais de ~30 builtins globais, ou uma operação que só faz sentido em um
domínio (I/O, matemática, texto) querendo entrar no prelúdio. A decisão de módulos em si
continua no [`TODO.md`](../../TODO.md) §11.

### 3. `str` e `repr` existem desde já

As duas funções entram agora, com papéis distintos:

```lox
print str("a")        # a
print repr("a")       # "a"
print str([1, "a"])   # [1, "a"]
print repr([1, "a"])  # [1, "a"]
print repr("a\nb")    # "a\nb"
```

- `str(x)` é a forma de **exibição**: string no topo sai sem aspas; números, `nil` e `bool`
  saem como em `print`; listas formatam elementos com strings citadas/escapadas.
- `repr(x)` é a forma de **debug**: string sempre citada/escapada; o resto usa a mesma
  formatação de `str` por enquanto. Em listas, `str` e `repr` coincidem hoje porque a
  formatação de elementos já cita strings.
- Ambas são aridade 1, aceitam qualquer valor e devolvem `String`; não há boxing.
- Hooks customizados (`__str__`/`__repr__` em classes) ficam para quando o modelo de
  objetos precisar; hoje a formatação é centralizada em `src/execution/values.py`.
- `repr` é determinístico: nada de endereço, `id` ou ordem de hash; ciclos de lista viram
  `[...]`.

### 4. Builtins são reservados no escopo global

Redefinir um builtin **no escopo global** é erro:

```lox
fn len(x) { return x; }   # erro: Can't redefine builtin 'len'.
val clock = 1;            # erro
class range {}            # erro
```

- No `--check`, o checker reporta `Can't redefine builtin 'x'.`
- Sem `--check`, o runtime recusa porque os builtins são definidos como **imutáveis**
  (`Environment.define(..., mutable=False)`), com a mensagem existente
  `Can't redeclare immutable variable 'x'.`
- **Shadowing local é permitido**: `fn f(len: Int)` ou `{ val str = 1; }` funcionam como
  sombreamento lexical normal; o builtin continua disponível fora daquele escopo.
- A lista canônica fica em [`src/execution/prelude.py`](../../src/execution/prelude.py) para checker e
  interpretador não divergirem.

### 5. Sem métodos em primitivos agora

`Int`, `Float`, `Bool`, `String` e `nil` continuam **primitivos sem métodos**. Não há
`5.toString()`, `s.upper()` nem `xs.len()`:

- `len(s)`, `str(x)`, `repr(x)` cobrem consultas genéricas;
- `List` tem métodos porque `LoxList` é um objeto de runtime, não um primitivo;
- métodos em primitivos exigiriam boxing (ou special-casing de `Get`) e encareceriam
  checker/codegen. Extensões/UFCS (P3) resolvem `s.upper()` depois **sem** boxing.

### 6. Extensões/UFCS ficam para P3, depois do LLVM MVP

Extensões são a saída para dar `s.minhaExtensao()` a funções sem inchar o tipo ou o
prelúdio, mas adicionam resolução de métodos, interação com traits e codegen. Ficam em P3,
depois do LLVM MVP, com gatilho: a stdlib precisar de uma operação em tipo existente ou
usuários pedirem. O item está registrado no [`TODO.md`](../../TODO.md) §1 e §8.

### 7. Conversões continuam em aberto

O modelo híbrido diz que conversão/constrói é "construtor namespaced", mas a **sintaxe
concreta** não foi decidida:

- `as` é candidato a **alias de import** (`import x as y`, estilo Python), então usar `as`
  também como cast pode ser confuso;
- alternativas para cast: `as` contextual, outra palavra (`to`, `cast`), ou método
  (`x.toInt()`);
- alternativas para parsing: `Int.parse("42") -> Option/Result`, `parse_int(s)` ou
  `to_int(s)`.

Nada disso entra neste ADR. Fica no [`TODO.md`](../../TODO.md) §11; a decisão será
tomada junto com módulos/`Option`/`Result` e a sintaxe de cast (`D-8` no
[`../spec/semantica.md`](../spec/semantica.md)).

## Consequências

### Positivas

- Uma regra única para decidir onde cada operação mora; menos "onde eu coloco isso?".
- `len`/`str`/`repr` funcionam em qualquer valor, sem métodos em primitivos e sem boxing.
- `List` pode ter `push`/`pop` sem abrir a porta para `5.toString()`.
- Builtins globais protegidos contra shadowing acidental; sombreamento local continua
  lexical e previsível.
- `str` e `repr` já dão ao usuário e ao debug formas distintas, sem esperar por classes com
  hooks.
- Prelúdio pequeno deixa espaço para `std.*` e para o codegen.

### Negativas / custos

- **Global ainda é promessa eterna**: cada builtin novo no prelúdio é difícil de remover.
- **Duas funções de formatação**: `str` e `repr` precisam ser mantidas e explicadas; em
  listas elas coincidem hoje, o que pode parecer redundante.
- **Shadowing global proibido** é uma mudança de comportamento: scripts que redefiniam
  `len`/`clock` passam a falhar (nenhum caso conhecido na suíte).
- **Conversões travadas** até a decisão de `as`/cast/parse; quem precisa de parse espera.
- **Extensões adiadas**: `s.upper()`/`xs.map()` como método não existem; a saída é função
  global (`len`, `str`, futuros `map`) por enquanto.
- **Sem hooks de `str`/`repr`**: classes não podem customizar a própria exibição ainda.

### Neutras

- `print` continua statement; `println` como função é uma decisão separada.
- `std.*` depende do sistema de módulos, ainda não implementado.
- Traits, `Option`/`Result` e generics de usuário continuam no roadmap e podem afetar a
  forma final de `Int.parse`/extensões.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Tudo global (estilo Python) | Ergonômico, mas polui o namespace, vira promessa eterna e mistura domínios (I/O, math, texto) no prelúdio. |
| Tudo método/UFCS | Primitivos precisam de boxing/special-casing; `nil` quebra; operações multi-tipo não pertencem a um operando; codegen mais caro. |
| Tudo em `std.*` importado por padrão | Organizado, mas exige módulos e ainda deixa nomes no escopo; cerimônia cedo demais. |
| Sem prelúdio; imports explícitos | Mais disciplinado, mas ruim para scripts e depende de módulos que não existem. |
| Permitir shadowing de builtin | Simples, mas é o footgun que motivou a pergunta; warning exigiria infraestrutura que ainda não existe. |
| Proibir shadowing em qualquer escopo | Rígido demais; impede sombreamento lexical normal e nomes comuns em parâmetros. |
| Métodos em primitivos com boxing | Uniformiza OO, mas cria boxing em `Int`/`String` e encarece checker/LLVM. |
| Extensões já em P2 | Melhora ergonomia cedo, mas adia o backend e aumenta a superfície antes do teste diferencial. |
| `int()`/`Int(...)` sobrecarregado | Três significados (parse, cast, default), difícil de tipar e de explicar; a discussão histórica já rejeitava. |

## Como verificar

- Golden cases:
  [`tests/cases/str_repr.lox`](../../tests/cases/str_repr.lox) e
  [`tests/cases/builtin_shadow_local.lox`](../../tests/cases/builtin_shadow_local.lox);
  erro em [`tests/cases/errors/builtin_redeclare.lox`](../../tests/cases/errors/builtin_redeclare.lox).
- Checker: [`tests/test_checker.py`](../../tests/test_checker.py) cobre `str`/`repr` como
  `String`, aridade e `Can't redefine builtin 'x'.` no global, além de shadowing local
  limpo.
- Determinismo: `str_repr.lox` entrou em
  [`tests/test_determinism.py`](../../tests/test_determinism.py).
- `make check` verde (ruff + mypy strict + pytest).

## Referências

- a discussão histórica de I-3 (git) — funções soltas vs métodos, argumentos e análise.
- [ADR-0015](0015-listas-tipadas.md) — primeiro caso real do modelo híbrido.
- [ADR-0014](0014-identidade-e-invariantes.md) — portão de admissão e I1–I3.
- [`docs/spec/semantica.md`](../spec/semantica.md) — comportamento de `len`/`str`/`repr`.
- Python FAQ e Guido (2006) — as razões de `len(x)` vs `x.len()` (links na discussão histórica de I-3).
- Kotlin/C# extension functions — o modelo de extensões que fica para P3.
