# ADR-0070 — Strings `"""` e raw (`r"..."`)

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0013](0013-ternario-nil-aware-escapes.md),
  [ADR-0019](0019-interpolacao.md), [ADR-0035](0035-strings-texto.md),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md)
- **Implementação:** `loxia_core/frontend/scanner.py`; casos
  `tests/cases/multiline_strings.lox`, `tests/cases/raw_strings.lox`,
  `tests/cases/errors/string_newline.lox`,
  `tests/cases/errors/unterminated_triple_string.lox`; testes em `tests/test_scanner.py`

## Contexto

A string de uma linha (`"..."`) já aceitava quebra de linha real — a documentação dizia
"podem conter quebras de linha reais". Isso significa que uma "string multilinha" já
existia, mas disfarçada: o mesmo delimitador, sem destaque visual, e sem como escrever
`"` sem escape. Raw strings não existiam: todo `\` era escape, então escrever um caminho
ou (no futuro) uma regex exigia duplicar barras.

O pedido foi: strings multilinha com forma canônica, raw strings e **uma** grafia por
conceito, no estilo Python `"""…"""`.

## Decisão

1. **`"..."` é de uma linha.** Quebra de linha real sem escape dentro de `"` vira erro
   dirigido: `Unterminated string; multiline strings use '"""'.` O scanner descarta o
   resto da linha para não gerar erros em cascata.
2. **`"""..."""` é a forma canônica de string multilinha.** Escapes continuam valendo
   (`\n`, `\t`, `\"`, `\\`, `\0`, `\$`, `\u{...}`); `"` e `""` podem aparecer livres; o
   fechamento é a primeira `"""`. `"""` **substitui** a string multilinha em `"..."` — não
   convivem duas grafias.
3. **Sem mágica de conteúdo:** nada de remover a primeira quebra de linha, nada de dedent
   automático. O valor é exatamente o que está entre os delimitadores (I2). Para começar
   sem newline, comece o conteúdo na mesma linha da abertura.
4. **Raw é prefixo `r` da mesma forma de string:** `r"..."` (uma linha) e `r"""..."""`
   (multilinha). Em raw **nada** é interpretado: `\` é literal e `${...}` não interpola.
   Um `"` isolado fecha a string raw de uma linha (não há `\"`); para conter `"`, use
   `r"""..."""`.
5. **Interpolação** `${...}` vale em `"` e `"""`; em raw é texto literal.
6. **`r` só é prefixo quando a aspa vem imediatamente depois** (`r"`, `r"""`); `r` sozinho
   continua identificador. Não existe `f"..."`.
7. **Contagem de linhas** acompanha o conteúdo, inclusive dentro de `"""`; o token é
   reportado na linha em que **termina**, comportamento que já existia.

## Consequências

### Positivas

- Uma forma só para multilinha, visualmente distinguível, e sem escapar toda aspa.
- Raw resolve `\` literal sem duplicar barras; e a regra "raw = nada é interpretado" é
  fácil de explicar e testar (escapes e interpolação desligados juntos).
- Nenhum custo no lowering: continua sendo o mesmo token `STRING`/`INTERPOLATED_STRING`
  com o conteúdo já decodificado; backend e checker não mudam.
- O erro de `"` multilinha ensina a forma canônica em vez de só falhar.

### Negativas / custos

- **Quebra deliberada**: programa que usava `"` com newline real agora não compila (com
  mensagem dirigida). No repositório não havia nenhum caso; a documentação e um golden
  foram atualizados.
- Raw não consegue conter `"""`; para isso é preciso `"""` normal com `\"`.
- `r` seguido imediatamente de `"` deixa de ser "identificador + string" (que nunca foi
  programa válido, mas muda a mensagem de erro).
- O scanner ganha dois parâmetros de estado (`raw`, `triple`) na função de string.

### Neutras

- O orçamento sintático não muda: nenhuma keyword (o `r` é prefixo lexical, não token),
  nenhum nível de precedência, nenhuma forma de statement/declaração, nenhuma regra de
  newline nova — string é um token só.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter `"` multilinha e somar `"""` | Duas grafias para o mesmo conceito — exatamente o que o ADR-0066 recusa. |
| Só `"""` e sem raw | `\` literal continua exigindo `\\`; raw era o pedido. |
| Raw só com `r"""` | Obriga delimitação tripla até para um caminho de uma linha. |
| `r` como palavra-chave | Não é sintaxe de statement; prefixo lexical não gasta orçamento de keyword. |
| Remover o primeiro newline (Python) | Mágica implícita contra o I2; quem não quer o newline começa o conteúdo na linha da abertura. |
| Dedent automático | Idem, e o custo de decidir "indentação comum" é surpresa em string de dados. |
| `'''` também | Segunda grafia de multilinha. |
| `f"..."` para interpolar | A interpolação já é `${...}` dentro de qualquer string; prefixo novo seria segunda grafia. |

## Como verificar

- `uv run python -m tests.runner multiline` e `raw_strings` (conteúdo, aspas e `${}`
  literal em raw);
- `uv run python -m tests.runner string_newline` e `unterminated_triple` (exit 65);
- `uv run pytest tests/test_scanner.py`;
- `uv run pytest tests/test_backend.py` (casos no corpus L3, mesmos bytes);
- `make check`.

## Referências

- [ADR-0013](0013-ternario-nil-aware-escapes.md) — tabela de escapes.
- [ADR-0019](0019-interpolacao.md) — `${...}` em qualquer expressão.
- [ADR-0035](0035-strings-texto.md) — strings como texto (code points, sem normalização).
- [ADR-0066](0066-orcamento-e-gate-sintatico.md) — gate e forma canônica.
