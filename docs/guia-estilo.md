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

`loxia fmt` é a forma canônica (ADR-0092 para o estilo, ADR-0136 para a engine):

- reflowa chamadas, listas, mapas, tuplas, params, enums, cadeias binárias/lógicas/`??`
  e condicionais para caber em **100 colunas** (`--max-width` 20..1000 é override de
  ferramenta/editor); strings, imports e comentários nunca são quebrados;
- decide a linha em branco: exatamente uma entre declarações de topo (`class`, `fn`,
  `interface`, `enum`, `type alias`), métodos de classe e de interface; `val`/`var` de
  topo e statements preservam no máximo uma linha do autor; nenhuma depois de `{`/antes
  de `}`;
- normaliza `# ` e alinha comentários trailing consecutivos no mesmo indent quando o
  alinhamento ainda cabe; `///` e `/* */` ficam verbatim (sem reflow);
- usa trailing comma em construtos multiline (menos enum e `match`, que a spec mantém
  sem), quebra binárias **depois** do operador e preserva C-style `for (;;)`;
- aceita vários arquivos e diretórios recursivos (`loxia fmt std tests/cases`), em ordem
  determinística; diretórios ocultos e caches (`node_modules`, `.venv`, …) ficam de fora;
  `--exclude GLOB` (repetível, relativo ao cwd; casa o path e seus ancestrais) tira
  diretórios/arquivos descobertos; use `**/nome/**` para qualquer profundidade. Um
  **arquivo** explícito sempre entra; um **diretório** explícito ainda respeita
  `--exclude`. Com erro de sintaxe em qualquer alvo **nada** é escrito (exit 65,
  diagnóstico por arquivo); nenhum alvo encontrado é uso (exit 2), path inexistente ou
  ilegível/não-UTF-8 é 66; `--check` é silencioso (65 > 1 > 0), `--diff` imprime um diff
  por arquivo; `--json` agrega os diagnósticos num único documento e `--json-lines` num
  único `start` + `summary`; labels são relativos ao cwd (basename fora dele, com sufixo
  de diretório se dois colidirem);
- `fmt --diff` mostra o diff unificado e não escreve; `fmt --check --edits=json` devolve
  o texto formatado e `TextEdit[]` com posições exatas (line/column 1-based, offset em
  bytes) para editores e agentes, sem reler o arquivo, e exige um único arquivo resolvido;
- não remove parênteses, não reordena imports, não normaliza aspas/números, não alinha
  `=`/`:` e não formata range/seleção (isso fica em #110).

No repositório, `loxia fmt .` encontra fixtures inválidas de propósito (`tests/cases/errors/`,
suíte oficial); use `--exclude` (por exemplo `--exclude 'tests/cases/errors/**'`) ou prefira
o gate `tests/test_formatter_repo.py` (`make check-fast`), que pula parse errors por
contrato.

O formatter de referência é Python ([ADR-0092](adr/0092-estilo-e-formatter.md),
[ADR-0136](adr/0136-formatter-2-doc-ir.md)); o dogfood em Lox fica adiado até o repo
público/estável.
