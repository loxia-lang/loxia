---
sources:
  - loxia_core/frontend/scanner.py
  - loxia_core/frontend/keywords.py
  - loxia_core/frontend/token_type.py
  - loxia_core/frontend/tokens.py
---

# Léxico

Como o código-fonte é dividido em tokens. Implementação: [`loxia_core/frontend/scanner.py`](../../loxia_core/frontend/scanner.py),
[`loxia_core/frontend/keywords.py`](../../loxia_core/frontend/keywords.py), [`loxia_core/frontend/token_type.py`](../../loxia_core/frontend/token_type.py).

## Arquivos

- Codificação: UTF-8 (é o que o `main.py` lê). Strings aceitam Unicode; `len`/índice
  contam code points ([ADR-0026](../adr/0026-freeze-1.0.md)).
- Identificadores são **ASCII** (`[A-Za-z_][A-Za-z0-9_]*`), sem normalização Unicode;
  Unicode é permitido em strings e comentários, não em identificadores
  ([ADR-0035](../adr/0035-strings-texto.md));
  `ação` ainda não é um nome válido. O scanner percorre a string Python.
- Não há BOM especial nem diretivas. Um arquivo `.lx` é um programa **ou um módulo**
  (arquivo = módulo, ADR-0073); uma primeira linha `#!` é só um comentário `#` normal.

## Espaços e comentários

- Ignorados: espaço, `\t`, `\r`.
- `\n` encerra a linha e incrementa o contador (linhas começam em **1**).
- Comentário de linha: `#` até o fim da linha.
- Comentário de documentação: `///` no início da linha (depois de espaços), uma ou mais
  linhas consecutivas imediatamente antes de uma declaração. O texto é Markdown; a
  primeira linha é o resumo. Linha em branco ou outro comentário quebra o vínculo; a doc
  é guardada na AST (`doc`) e **não** vira token nem chega ao runtime ([ADR-0091](../adr/0091-doc-comments-e-geracao-de-docs.md)).
  `///` só é doc no início da linha; `//` continua sendo divisão inteira.
- Comentário de bloco: `/* ... */`, **aninhado** (`/* /* */ */`); bloco não fechado é
  `Unterminated block comment.` e conta as linhas internas.
- Comentários aparecem em qualquer lugar entre tokens (inclusive no fim de linha); `#`
  dentro de string não é comentário. Não existe `--`.
- `//` **não** é comentário: é o operador de divisão inteira. Onde se espera uma
  expressão, `//` gera um erro dirigido (`'//' is integer division, and comments start
  with '#'`) em vez do genérico `Expect expression.`

## Tokens

### Um caractere

```
(   )   {   }   ,   .   -   +   ;   /   *   %   |   &   ^   ~
```

### Um ou dois caracteres

```
!=          =    ==
<    <=          >    >=
.    ..    ...   -    ->
/    //          *    **
<    <<          >    >>    >>>
?    ??          ?.
```

`//` é divisão inteira; `/` sozinho é divisão `Float`. `..` é o operador de range
(`0..10`) e `...` é o prefixo de variádico/spread (`...xs`, `f(...xs)`); não existe `..=`.
`?` é o sufixo de tipo opcional; `??` é coalescência e `?.` é optional chaining. `#` e
`/*` iniciam comentários, não tokens.

### Literais

| Token | Regra | Valor |
| --- | --- | --- |
| `NUMBER` | ver abaixo | `int` (i64) ou `float` (f64) |
| `STRING` | `"` … `"` | `str` com o conteúdo entre aspas |
| `IDENTIFIER` | `ALPHA ( ALPHA \| DIGIT )*` | lexema |

```
DIGIT   → "0" … "9"
ALPHA   → "a" … "z" | "A" … "Z" | "_"
```

Números ([ADR-0006](../adr/0006-int-float-separados.md)):

- **`Int`**: `DIGIT+` com `_` opcional entre dígitos (`42`, `1_000_000`), ou base
  `0x`/`0X` (hex), `0b`/`0B` (binário) e `0o`/`0O` (octal) — `0xFF` = 255, `0b1010` = 10,
  `0o755` = 493;
- **`Float`**: tem `.` com dígito dos dois lados e/ou expoente (`3.14`, `1e9`, `1.5e-3`,
  `1.0`);
- `1` é `Int`, `1.0` é `Float`; não há sufixos (`1i64`, `1.0f32`) nem sinal no literal
  (o `-` é operador unário);
- `_` só entre dígitos: `1__0`, `_1` e `1_` são erro;
- `.5` e `1.` não são números (`1.` lê `1` e depois `.`, erro de sintaxe); bases não
  aceitam `.` nem expoente;
- magnitude máxima de `Int` é `9223372036854775807` (`2^63 - 1`); literal maior é erro de
  compilação. `INT_MIN` não tem literal próprio: use `-9223372036854775807 - 1`;
- `1..10` (range) existe: o scanner exige dígito depois do `.` de um float exatamente para
  não engolir o `..`;
- `Float` é IEEE-754 binary64; um literal que estoura vira `inf` (comportamento do Python).

Strings ([ADR-0070](../adr/0070-strings-multilinha-e-raw.md)):
- `"..."` é de **uma linha**; quebra de linha real dentro dela é
  `Unterminated string; multiline strings use '"""'.` (o scanner descarta o resto da
  linha para não gerar erros em cascata);
- `"""..."""` é a forma canônica de string **multilinha**: pode conter `"` e `""` livres e
  fecha na primeira `"""`; nada de remover a primeira quebra de linha nem dedent — o valor
  é exatamente o que está entre os delimitadores (I2); sem fechar → `Unterminated string.`;
- `r"..."` e `r"""..."""` são **raw**: `\` é literal e `${...}` **não** interpola. O `r`
  só é prefixo quando a aspa vem imediatamente depois; `r` sozinho é identificador;
- `"..."` e `"""..."""` aceitam `\n`, `\t`, `\r`, `\"`, `\\`, `\0`, `\$` e `\u{XXXX}`
  (code point Unicode); escape desconhecido é `Unknown escape sequence '\q'.`; `\u`
  inválido é `Invalid Unicode escape.`;
- `${expressão}` interpola uma expressão (qualquer uma, inclusive outra string
  interpolada); os tokens da expressão são escaneados em um buffer próprio e o `}` de
  fechamento não entra nele. `\$` e `\${` produzem `$`/`${` literais; `$` sem `{` é
  literal;
- o contador de linha acompanha o conteúdo, inclusive dentro de `"""`; o token é reportado
  na linha em que termina.

### Palavras-chave

```
and    as     async  await  class  elif   else   enum   except
false  finally fn    for    if     in     interface is  match
nil    not    or     raise  return super  this   true
try    val    var    while
```

`not` é a negação (ADR-0068); `!` sozinho não é token — o scanner aponta
`Unexpected character: ! (use 'not' for negation).` e `!=` continua sendo desigualdade.

`fn` substituiu `fun`; `fun` agora é identificador comum (não é palavra-chave).

São sensíveis a maiúsculas (`Class` é identificador).

`async` e `await` estão **reservadas** como preparação do assincronismo
([ADR-0037](../adr/0037-async-direcao.md)); ainda não têm sintaxe, então usá-las como
identificador é erro de compilação.

### Fim de arquivo

Sempre existe um token `EOF`, com a linha atual. O parser depende dele.

## Erros do léxico

| Situação | Mensagem | Consequência |
| --- | --- | --- |
| caractere fora do alfabeto | `Unexpected character: X` | erro de compilação (exit 65) |
| `!` sozinho (fora de `!=`) | `Unexpected character: ! (use 'not' for negation).` | erro de compilação (exit 65) |
| string sem fechamento (EOF ou `"""` aberta) | `Unterminated string.` | erro de compilação (exit 65) |
| quebra de linha em `"..."` | `Unterminated string; multiline strings use '"""'.` | erro de compilação (exit 65) |
| interpolação sem `}` | `Unterminated interpolation.` | erro de compilação (exit 65) |
| escape desconhecido | `Unknown escape sequence '\q'.` | erro de compilação (exit 65) |
| `\u{...}` inválido | `Invalid Unicode escape.` | erro de compilação (exit 65) |
| literal numérico malformado (`1__0`, `0x` sem dígitos) | `Invalid number literal.` | erro de compilação (exit 65) |
| literal `Int` acima de `2^63 - 1` | `Too large integer literal.` | erro de compilação (exit 65) |

Depois de um erro o scanner continua; o parser pode reportar mais erros na mesma execução.
