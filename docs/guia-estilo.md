# Guia de estilo da Loxia

Norma para código Loxia. Decisão e escopo do formatter no
[ADR-0092](adr/0092-estilo-e-formatter.md); doc comments no
[ADR-0091](adr/0091-doc-comments-e-geracao-de-docs.md).

## Nomes

| Construção | Convenção | Exemplo |
| --- | --- | --- |
| classe, interface, enum, type alias | `PascalCase` | `Result`, `Shape` |
| função, método, variável, parâmetro, campo | `camelCase` | `isEmpty`, `items` |
| enum de constantes (sem payload) | variantes `UPPER_SNAKE` | `Cor.AMARELO` |
| enum soma (alguma variante com payload) | todas as variantes `PascalCase` | `Result.Ok` |
| parâmetro de tipo | letra maiúscula | `T`, `K`, `V`, `E` |
| membro privado | prefixo `_` | `_isSpace` |
| arquivo/módulo | `snake_case.lx` | `std/json.lx` |

A regra de enum é por enum: `Cor` (sem payload) usa `AMARELO`; `Result` (com payload)
usa `Ok`/`Err`. Identificadores públicos da stdlib e builtins são em inglês; código de
usuário pode usar o idioma do domínio. O formatter **não renomeia**; revisão/lint cuidam
disso.

## Formatação

- UTF-8, LF, newline final, sem espaço no fim da linha.
- **2 espaços**; nunca tabs.
- **100 colunas**; strings/imports/doc podem exceder.
- K&R: `{` na mesma linha; `}` sozinho; `} elif (c) {`, `} else {`.
- `;` opcional **omitido** no fim da linha; uma instrução por linha.
- `fn` obrigatório no topo e **mantido em método** (`fn metodo(...)`).
- Aspas duplas; raw/multilinha só quando necessário.
- Trailing comma em lista/mapa/tupla/params/call multiline.
- 1 linha em branco entre declarações/membros; no máximo 2 entre seções.
- Imports no topo, antes de declarações; grupos std → locais; sem reordenar.
- `#` para comentário de implementação; `///` para doc (Markdown); `/* */` para bloco.

## Formatter

`loxia fmt` normaliza, na fase 1: indentação de bloco, espaços no fim, `;` de fim de
linha e newline final, preservando quebras, strings multilinha, comentários de bloco e o
conteúdo de comentários. Não faz reflow, não renomeia, não reordena imports e não insere
`fn` em método ainda; essas regras são norma até a fase seguinte. `loxia fmt --check`
não escreve e retorna 1 se o arquivo mudaria.

O formatter de referência é Python ([ADR-0092](adr/0092-estilo-e-formatter.md)); o
dogfood em Lox entra depois da T3, com paridade byte a byte contra esta referência.
