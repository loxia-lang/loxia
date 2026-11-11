# Léxico

Como o código-fonte é dividido em tokens. Implementação: [`src/scanner.py`](../../src/scanner.py),
[`src/keywords.py`](../../src/keywords.py), [`src/token_type.py`](../../src/token_type.py).

## Arquivos

- Codificação: UTF-8 (é o que o `main.py` lê).
- O scanner trabalha **byte a byte sobre a string Python**; identificadores são ASCII.
- Não há BOM especial, diretivas nem módulos: um arquivo `.lox` é um programa. Uma
  primeira linha `#!` é só um comentário `#` normal.

## Espaços e comentários

- Ignorados: espaço, `\t`, `\r`.
- `\n` encerra a linha e incrementa o contador (linhas começam em **1**).
- Comentário de linha: `#` até o fim da linha.
- Comentário de bloco: `/* ... */`, **aninhado** (`/* /* */ */`); bloco não fechado é
  `Unterminated block comment.` e conta as linhas internas.
- Comentários aparecem em qualquer lugar entre tokens (inclusive no fim de linha); `#`
  dentro de string não é comentário. Não existe `--`.

## Tokens

### Um caractere

```
(   )   {   }   ,   .   -   +   ;   /   *   %   |   &   ^   ~
```

### Um ou dois caracteres

```
!    !=          =    ==
<    <=          >    >=
.    ..          -    ->
/    //          *    **
<    <<          >    >>    >>>
```

`//` é divisão inteira; `/` sozinho é divisão `Float`. `..` é o operador de range
(`0..10`); não existe `..=`. `#` e `/*` iniciam comentários, não tokens.

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

Números ([`../../TIPOS.md`](../../TIPOS.md) §3, [ADR-0006](../adr/0006-int-float-separados.md)):

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

Strings:
- não têm escapes: `"\n"` é barra + `n`, não quebra de linha;
- podem conter quebras de linha reais (o contador de linha acompanha);
- `"` não escapado encerra; sem fechar → `Unterminated string.`;
- não há interpolação nem raw strings.

### Palavras-chave

```
and    class  elif   else   false  for
fn     if     in     nil    or     print
return super  this   true   val    var
while
```

`fn` substituiu `fun`; `fun` agora é identificador comum (não é palavra-chave).

São sensíveis a maiúsculas (`Class` é identificador).

### Fim de arquivo

Sempre existe um token `EOF`, com a linha atual. O parser depende dele.

## Erros do léxico

| Situação | Mensagem | Consequência |
| --- | --- | --- |
| caractere fora do alfabeto | `Unexpected character: X` | erro de compilação (exit 65) |
| string sem fechamento | `Unterminated string.` | erro de compilação (exit 65) |
| literal numérico malformado (`1__0`, `0x` sem dígitos) | `Invalid number literal.` | erro de compilação (exit 65) |
| literal `Int` acima de `2^63 - 1` | `Too large integer literal.` | erro de compilação (exit 65) |

Depois de um erro o scanner continua; o parser pode reportar mais erros na mesma execução.
