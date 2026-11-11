# Léxico

Como o código-fonte é dividido em tokens. Implementação: [`src/scanner.py`](../../src/scanner.py),
[`src/keywords.py`](../../src/keywords.py), [`src/token_type.py`](../../src/token_type.py).

## Arquivos

- Codificação: UTF-8 (é o que o `main.py` lê).
- O scanner trabalha **byte a byte sobre a string Python**; identificadores são ASCII.
- Não há BOM especial, diretivas, `#!` nem módulos: um arquivo `.lox` é um programa.

## Espaços e comentários

- Ignorados: espaço, `\t`, `\r`.
- `\n` encerra a linha e incrementa o contador (linhas começam em **1**).
- Comentário de linha: `//` até o fim da linha. **Não existe** comentário de bloco.
- Comentários aparecem em qualquer lugar entre tokens (inclusive no fim de linha).

## Tokens

### Um caractere

```
(   )   {   }   ,   .   -   +   ;   /   *
```

### Um ou dois caracteres

```
!    !=
=    ==
<    <=
>    >=
```

`//` é comentário; `/` sozinho é divisão.

### Literais

| Token | Regra | Valor |
| --- | --- | --- |
| `NUMBER` | `DIGIT+ ( "." DIGIT+ )?` | `float` (IEEE-754 double) |
| `STRING` | `"` … `"` | `str` com o conteúdo entre aspas |
| `IDENTIFIER` | `ALPHA ( ALPHA \| DIGIT )*` | lexema |

```
DIGIT   → "0" … "9"
ALPHA   → "a" … "z" | "A" … "Z" | "_"
```

Números (detalhes em [`../../TIPOS.md`](../../TIPOS.md)):
- `123` vira `123.0` — **todo número é `Float` hoje**;
- sem expoente (`1e9`), sem hexadecimal/binário, sem `_`, sem sinal (o `-` é operador);
- `1.` e `.5` não são números válidos;
- `123.456` é aceito; `123.` lê `123` e depois `.` (erro de sintaxe no `primary`).

Strings:
- não têm escapes: `"\n"` é barra + `n`, não quebra de linha;
- podem conter quebras de linha reais (o contador de linha acompanha);
- `"` não escapado encerra; sem fechar → `Unterminated string.`;
- não há interpolação nem raw strings.

### Palavras-chave

```
and   class   else   false   for   fun     if    nil
or    print   return  super   this  true    val   var   while
```

São sensíveis a maiúsculas (`Class` é identificador).

### Fim de arquivo

Sempre existe um token `EOF`, com a linha atual. O parser depende dele.

## Erros do léxico

| Situação | Mensagem | Consequência |
| --- | --- | --- |
| caractere fora do alfabeto | `Unexpected character: X` | erro de compilação (exit 65) |
| string sem fechamento | `Unterminated string.` | erro de compilação (exit 65) |

Depois de um erro o scanner continua; o parser pode reportar mais erros na mesma execução.
