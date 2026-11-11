# Sintaxe

Gramática do parser atual ([`src/parser.py`](../../src/parser.py)) — recursive descent,
uma função por nível de precedência.

> Isto é o **Lox implementado**. A sintaxe alvo da linguagem própria (`fn`, `;` opcional,
> `?.`, `??`…) está em [`../../TODO.md`](../../TODO.md) §1 e **não** existe no parser
> hoje. `val`/`var` já existem (ADR-0005).

## Gramática (EBNF)

```ebnf
program        → declaration* EOF ;

declaration    → classDecl
               | funDecl
               | varDecl
               | valDecl
               | statement ;

classDecl      → "class" IDENTIFIER ( "<" IDENTIFIER )? "{" function* "}" ;
funDecl        → "fun" function ;
function       → IDENTIFIER "(" parameters? ")" block ;
parameters     → parameter ( "," parameter )* ;
parameter      → "var"? IDENTIFIER ;

varDecl        → "var" IDENTIFIER ( "=" expression )? ";" ;
valDecl        → "val" IDENTIFIER "=" expression ";" ;

statement      → exprStmt
               | forStmt
               | ifStmt
               | printStmt
               | returnStmt
               | whileStmt
               | block ;

exprStmt       → expression ";" ;
forStmt        → "for" "(" ( varDecl | valDecl | exprStmt | ";" )
                 expression? ";"
                 expression? ")" statement ;
ifStmt         → "if" "(" expression ")" statement ( "else" statement )? ;
printStmt      → "print" expression ";" ;
returnStmt     → "return" expression? ";" ;
whileStmt      → "while" "(" expression ")" statement ;
block          → "{" declaration* "}" ;

expression     → assignment ;
assignment     → ( call "." )? IDENTIFIER "=" assignment
               | logic_or ;
logic_or       → logic_and ( "or" logic_and )* ;
logic_and      → equality ( "and" equality )* ;
equality       → comparison ( ( "!=" | "==" ) comparison )* ;
comparison     → term ( ( ">" | ">=" | "<" | "<=" ) term )* ;
term           → factor ( ( "-" | "+" ) factor )* ;
factor         → unary ( ( "/" | "*" | "%" ) unary )* ;
unary          → ( "!" | "-" ) unary | call ;
call           → primary ( "(" arguments? ")" | "." IDENTIFIER )* ;
arguments      → expression ( "," expression )* ;
primary        → "true" | "false" | "nil" | "this"
               | NUMBER | STRING | IDENTIFIER | "(" expression ")"
               | "super" "." IDENTIFIER ;
```

## Precedência e associatividade

Do menor para o maior:

| Nível | Operadores | Associatividade |
| --- | --- | --- |
| atribuição | `=` | direita |
| or | `or` | esquerda |
| and | `and` | esquerda |
| igualdade | `==` `!=` | esquerda |
| comparação | `<` `<=` `>` `>=` | esquerda |
| termo | `+` `-` | esquerda |
| fator | `*` `/` `%` | esquerda |
| unário | `!` `-` | direita |
| chamada | `()` `.` | encadeia à esquerda |
| primário | literais, `this`, `super.x`, `( … )` | — |

Consequências:
- `-a.b()` = `-(a.b())` — a chamada liga mais forte que o unário;
- `a = b = c` atribui da direita para a esquerda;
- `a or b and c` = `a or (b and c)`;
- `!a == b` = `(!a) == b`.

`<` tem dois papéis sintáticos: comparação em expressões e **herança** logo após o nome da
classe (`class B < A`). Não há ambiguidade porque o parser de classe consome o `<` antes do
corpo.

## Açúcar sintático

### `for` vira `while`

Não existe nó de `for` na AST. O parser desaçucara:

```lox
for (var i = 0; i < 3; i = i + 1) print i;
```

vira

```lox
{
  var i = 0;
  while (i < 3) {
    print i;
    i = i + 1;
  }
}
```

Por isso o `for` tem as mesmas regras de escopo de um bloco e uma condição omitida vira
`true` (laço infinito).

### Blocos

`{ … }` é um statement; expressões não têm bloco. `if`/`while` recebem **um** statement
(por isso as chaves quando há mais de uma instrução).

## Pontos finos

- **Ponto e vírgula é obrigatório** em `var`, `print`, `return`, `for` e expressões, exceto
  no REPL: no modo `repl=True`, o `;` final pode ser omitido quando a entrada termina
  (`_end_statement`). Declarações continuam precisando de `;` no meio do arquivo.
- `val` **exige inicializador** (`val x;` é erro). `var` pode omitir (`var x;` → `nil`).
- Parâmetros são **`val` implícitos**; `var` antes do nome libera a reatribuição:
  `fun f(x, var y)`. `val` explícito em parâmetro não é aceito.
- Métodos de classe **não usam `fun`**:

  ```lox
  class Foo {
    bar(a) { return a; }
  }
  ```

- Limites do parser: no máximo **255 argumentos** por chamada e **255 parâmetros** por
  função. Ao ultrapassar, o erro é reportado mas o parser continua (os argumentos são
  descartados da AST).
- `this` e `super` são palavras-chave: `super` só aparece como `super.metodo`.
- Não existem: `break`/`continue`, `switch`, `match`, `elif`, operador ternário, arrays,
  mapas, `+=`, `++`, `import`, `try/catch`, interpolação, funções anônimas (challenge #2
  pendente).
- `fun` pode aparecer em qualquer posição de declaração, inclusive dentro de bloco.
