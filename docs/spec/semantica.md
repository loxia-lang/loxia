# Semântica

Comportamento observável do interpretador. Implementação: [`src/interpreter.py`](../../src/interpreter.py),
[`src/resolver.py`](../../src/resolver.py), [`src/environment.py`](../../src/environment.py),
[`src/lox_function.py`](../../src/lox_function.py), [`src/lox_class.py`](../../src/lox_class.py),
[`src/lox_instance.py`](../../src/lox_instance.py), [`src/values.py`](../../src/values.py).

## Execução

Um programa é uma lista de declarações executadas **em ordem**. Um erro de compilação
(léxico, sintaxe ou resolver) impede a execução inteira. Um erro de runtime interrompe o
programa no ponto em que ocorreu; o que já foi impresso permanece.

O REPL executa uma linha por vez, **mantendo variáveis, funções e classes** entre linhas.
Uma expressão pura como `1 + 1` é embrulhada em `print` e mostra `2`; declarações
(`var`, `fun`, `class`) não imprimem nada.

## Valores

| Valor | Origem | `stringify` |
| --- | --- | --- |
| `nil` | `nil`, `var` sem inicializador, `return;` | `nil` |
| `true`/`false` | literais, comparações | `true`/`false` |
| `Int` | literais sem `.`/expoente, aritmética inteira | decimal (`42`, `-3`) |
| `Float` | literais com `.`/expoente, `/`, mistura com `Float` | round-trip (`42.0`, `2.5`) |
| string | literais, `+` | conteúdo |
| função | `fun` | `<fn nome>` |
| função nativa | `clock` | `<native fn>` |
| classe | `class` | nome da classe |
| instância | chamada de classe | `Nome instance` |

Números são **`Int` (i64) ou `Float` (f64)** — [ADR-0006](../adr/0006-int-float-separados.md).
`print 3;` mostra `3` e `print 3.0;` mostra `3.0`: o tipo vem do literal. Detalhes das
regras em [`../../TIPOS.md`](../../TIPOS.md) §3.

### Truthiness

Só `nil` e `false` são falsos. `0`, `0.0`, `""` e listas (quando existirem) são **verdadeiros**.

### Igualdade (`==`, `!=`)

- `nil == nil` → `true`; `nil` vs qualquer outro → `false`;
- `Int` e `Float` comparam por valor numérico, com promoção: `1 == 1.0` → `true` (o `Int`
  é convertido para `Float`; acima de `2^53` a conversão pode perder precisão, como no
  LLVM);
- `true == 1` → `false` (booleano nunca é número);
- strings comparam por conteúdo;
- funções, classes e instâncias comparam por **identidade** (o mesmo objeto);
- `NaN != NaN` (IEEE); nenhum literal produz `NaN` hoje.

### Formatação de números

- `Int` → decimal, sem casas (`42`, `-3`);
- `Float` → menor representação que volta ao mesmo `double`, **sempre** distinguindo de
  `Int`: `2.0`, `-0.0`, `3.14`, `0.30000000000000004`;
- notação científica do Python a partir da magnitude correspondente (`1e+20`, `1e-07`);
- `NaN`, `inf` e `-inf` são os textos de `Float` não finitos; `inf` só aparece por
  overflow de `Float` (divisão por zero é erro);
- a formatação é contrato dos golden cases: `42` e `42.0` são saídas diferentes.

## Variáveis, `val` e `var`

- `val x = expr;` cria binding **imutável** e **exige inicializador**.
- `var x;` cria binding mutável com `nil`; `var x = expr;` idem com valor.
- A imutabilidade é do **nome**, não do valor: `val lista` (quando listas existirem) ainda
  pode ter conteúdo mutável.
- Atribuir a `val` local (ou a parâmetro imutável) é **erro de compilação**:
  `'x' is immutable; declare it with 'var' to allow assignment.`
- Atribuir a `val` **global** é erro de **runtime** (mesma mensagem, exit 70): globais não
  são rastreadas pelo resolver.
- `val` global **não pode ser redeclarado** (`val x = 1; var x = 2;`): erro de runtime
  `Can't redeclare immutable variable 'x'.` `var` global continua redeclarável; `var`
  seguido de `val` é permitido e o nome passa a ser imutável.
- Em escopo local (bloco, função, `for`), redeclarar o mesmo nome no mesmo escopo é erro de
  compilação: `Already a variable with this name in this scope.` (vale para `val` e `var`).
- Blocos aninhados podem **sombrear** nomes de escopos externos (inclusive `val`).
- Ler variável local no próprio inicializador é erro:
  `Can't read local variable in its own initializer.` (global vira
  `Undefined variable` em runtime).
- Declarações `fun` e `class` criam bindings **mutáveis** (decisão separada em aberto).
- O resolver grava a **distância** de cada acesso local; variáveis globais continuam sendo
  buscadas em runtime no ambiente global. Isso garante escopo léxico: uma closure lê a
  variável do local onde foi **declarada**, não do local de onde é chamada.

Exemplo canônico:

```lox
var a = "global";
{
  fun showA() { print a; }
  showA();        // global
  var a = "block";
  showA();        // global (não "block")
}
```

## Operadores

| Operador | Tipos | Resultado |
| --- | --- | --- |
| `!` | qualquer | nega a truthiness |
| `-` | número | negação (em `Int`, com wrapping) |
| `+` | dois números **ou** duas strings | soma com promoção / concatenação |
| `-` `*` | dois números | aritmética com promoção; `Int` faz wrapping |
| `/` | dois números | divisão **sempre `Float`** (`4 / 2` → `2.0`) |
| `%` | dois números | resto truncado (sinal do dividendo); `fmod` se houver `Float` |
| `<` `<=` `>` `>=` | dois números | booleano (promoção; com `NaN`, tudo `false`) |
| `==` `!=` | qualquer | igualdade |
| `and` `or` | qualquer | curto-circuito, devolve o operando |

- `Int op Float` promove o `Int` para `Float` (`1 + 2.0` → `3.0`); `Float → Int` nunca é
  implícito.
- `+` **não** mistura número e string: `Operands must be two numbers or two strings.`
- Comparações relacionais são só numéricas: `Operands must be numbers.`
- Divisão por zero é **erro de runtime** (`Division by zero not allowed`), para `Int` e
  `Float` — decisão nossa, diferente do livro (que devolveria `inf`/`NaN`).
- Resto por zero também é erro de runtime (`Modulo by zero not allowed`).
- `%` segue C/LLVM: `-7 % 3` → `-1` (sinal do dividendo), não `2`.
- A divisão inteira `//` **não existe**: colide com o comentário `//` e o token ainda
  está em aberto ([`../../TIPOS.md`](../../TIPOS.md) `D-4`).
- `and`/`or` devolvem o valor do operando, não um booleano:
  `nil or 2` → `2`; `false and 1` → `false`.
- A ordem de avaliação é esquerda→direita; `and`/`or` só avaliam a direita se necessário.

## Statements

| Statement | Efeito |
| --- | --- |
| `print expr;` | avalia e imprime com `stringify` + `\n` |
| `expr;` | avalia e descarta |
| `{ … }` | novo escopo |
| `if (c) s else s` | executa o ramo conforme truthiness |
| `while (c) s` | repete enquanto truthy |
| `for (init; cond; incr) s` | desaçucarado para bloco + `while` (ver sintaxe) |
| `return expr?;` | desempilha até a chamada da função |

## Funções

- Declaração: `fun nome(params) { corpo }`; o nome é definido **antes** do corpo, então a
  função pode ser recursiva; funções no mesmo escopo podem se chamar (resolução em runtime
  para globais, distância para locais).
- Parâmetros são **imutáveis por padrão** (`val` implícito). `fun f(var x)` permite
  reatribuir `x`; sem `var`, a atribuição é erro de compilação.
- Chamada: avalia o **callee** primeiro e os argumentos da esquerda para a direita; depois
  verifica se é chamável e a aridade.
- Não é chamável: `Can only call functions and classes.`
- Aridade errada: `Expected N arguments but got M.`
- Closures: a função captura o ambiente onde foi **declarada** (por referência). Variáveis
  capturadas continuam mutáveis.
- `return;` devolve `nil`. `return` no topo do programa é erro de compilação:
  `Can't return from top-level code.`
- Parâmetros e locais do corpo compartilham o mesmo escopo: declarar `var a` quando existe
  parâmetro `a` é erro (mesma mensagem de redeclaração).
- `clock()` é a única nativa: devolve segundos desde a época como `float`, aridade 0.

## Classes

```lox
class Conta {
  init(saldo) {
    this.saldo = saldo;
  }

  deposita(v) {
    this.saldo = this.saldo + v;
  }
}

class ContaPoupanca < Conta {
  render() {
    this.saldo = this.saldo * 1.1;
  }
}
```

- `class Nome { métodos }` cria a classe e a liga ao nome no escopo atual.
- Métodos **não** usam `fun`; são funções com `this` ligado.
- `Nome(args)` cria instância, executa `init` (se existir) e devolve a instância.
  A aridade da classe é a do `init` (0 se não houver).
- `init` devolve sempre a instância: `return;` é permitido, `return valor;` é erro de
  compilação (`Can't return a value from an initializer.`).
- `this` só existe dentro de métodos; fora de classe é erro de compilação
  (`Can't use 'this' outside of a class.`).
- Campos são dinâmicos: `obj.x = 1` cria/atualiza; campos têm prioridade sobre métodos na
  leitura.
- Ler propriedade que não é campo nem método: `Undefined property 'x'.`
- `obj.campo = v` exige instância: `Only instances have fields.`
- Ler propriedade de não-instância: `Only instances have properties.`
- Método lido como valor continua ligado à instância (`var f = obj.m; f();`).

### Herança

- Sintaxe: `class B < A` (herança simples; a decisão `extends` fica para a linguagem final).
- Métodos e `init` são herdados; o método da subclasse **sobrescreve** o da superclasse.
- `super.metodo(args)` busca `metodo` na superclasse e o liga ao `this` atual (não ao
  "this da superclasse").
- `super` só pode aparecer dentro de método de classe **com** superclasse:
  - fora de classe → `Can't use 'super' outside of a class.`
  - classe sem superclasse → `Can't use 'super' in a class with no superclass.`
- Herdar de si mesma → erro de compilação: `A class can't inherit from itself.`
- Superclasse precisa ser classe em runtime: `Superclass must be a class.`
- `super.metodo` inexistente → `Undefined property 'metodo'.`

## Erros

| Fase | Quando | Exit code (arquivo) |
| --- | --- | --- |
| léxico/sintaxe/resolver | antes de executar | **65** |
| runtime | durante a execução | **70** |
| arquivo não encontrado | antes de tudo | **66** |

- Formato de compilação: `[line N] Error at 'token': mensagem` (ou `at end`).
- Formato de runtime: `mensagem` + `[line N]`.
- Mensagens são em inglês (compatibilidade com o livro e testes).
- Erros de compilação são **acumulados** (parser tenta se recuperar; resolver reporta todos);
  erros de runtime param no primeiro.
- Ainda **não há** colunas, spans, stack trace, códigos de erro nem JSON — plano em
  [`../../TODO.md`](../../TODO.md) §3.1.
- No REPL, cada linha começa com estado de erro limpo e o ambiente permanece.

## Diferenças conscientes em relação ao livro

- Divisão por zero é erro (o livro devolve `inf`).
- O REPL aceita `;` final opcional e imprime o valor de expressões.
- `return` no topo é erro de compilação já no cap. 11 (no livro, o resolver faz isso).
- Números são `Int` e `Float` separados (o livro usa só `float`); `/` é sempre `Float`,
  `%` é truncado e `Int` faz wrapping — ver [ADR-0006](../adr/0006-int-float-separados.md).
- `val`/`var` não existem no livro (que só tem `var` mutável); ver [ADR-0005](../adr/0005-val-var-imutabilidade.md).

Tudo o mais segue o jlox do livro, inclusive as mensagens.
