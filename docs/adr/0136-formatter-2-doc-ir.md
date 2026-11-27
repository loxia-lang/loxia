# ADR-0136 — Formatter 2.0: Doc IR, wrapping e edições estruturadas

- **Status:** accepted (fase 2 implementada em 2026-11-23)
- **Data:** 2026-11-23
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0092](0092-estilo-e-formatter.md) (fase 1 e guia de estilo),
  [ADR-0134](0134-trivia-side-table.md) (trivia/attachment),
  [ADR-0129](0129-oraculo-do-front-end.md) (oráculo e hashes),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (forma canônica),
  [issue #109](https://github.com/loxia-lang/loxia/issues/109),
  [tracker #102](https://github.com/loxia-lang/loxia/issues/102)
- **Implementação:** `loxia/formatter/doc.py`, `comments.py`, `printer.py`, `engine.py` e
  `edits.py`; `tests/test_formatter_doc.py`, `tests/test_formatter_v2.py`,
  `tests/test_formatter.py` e `tests/test_formatter_edits.py`;
  `tests/oracle/frontend.json` (seção `fmt`), `docs/guia-estilo.md`,
  `docs/spec/sintaxe.md` e `README.md`

## Contexto

O formatter da fase 1 (ADR-0092) normaliza indentação, `;`, `fn` em método, vírgula
trailing e newline final, mas **preserva as quebras do autor**: não reflow, não decide
linha em branco e não tem noção estrutural de comentário. Ele edita linhas, não nós.

O #108 entregou a side table de trivia com attachment determinístico (ADR-0134) e o #106
entregou `NodeSpan`; o #107 publicou o AST JSON v2. Com isso, o formatter pode responder
“qual comentário pertence a este item”, “quantas linhas em branco o autor deixou” e
“onde quebrar sem deixar comentário órfão” — as perguntas que a fase 1 não sabia fazer.

O #109 pede a primeira tranche: wrapping por largura, política de linhas em branco,
normalização/alinhamento de comentários trailing, `--max-width` e edits estruturados.
Sem uma decisão de layout, cada regra viraria uma heurística de linha diferente.

## Decisão

1. **Doc IR + camada de itens.** O layout intra-item é uma árvore de documentos
   (`Text`, `Concat`, `Line`, `SoftLine`, `HardLine`, `BlankLine`, `EnsureLine`, `Indent`,
   `Group`, `IfBreak`, `TrailingComment`); o renderer decide plano/quebrado por grupo com
   uma varredura limitada por largura. Entre itens (declaração, membro, statement, arm)
   vale uma camada de política: linhas em branco, alinhamento e posição de comentários.
2. **O layout é função da AST + trivia + largura**, não das quebras do autor. A exceção
   deliberada é a linha em branco preservada (≤ 1) e o comentário, que é hard break.
3. **Largura 100**, `--max-width` como override de ferramenta/editor (20..1000) e, no
   LSP, `loxia.formatter.maxWidth` via `initializationOptions`/`didChangeConfiguration`;
   sem `.loxiafmt` e sem config por projeto. Strings, imports e comentários nunca são
   quebrados.
4. **Forma canônica:** chamadas, listas, mapas, tuplas, params e enums quebram
   verticalmente quando não cabem, com trailing comma (enums e `match` ficam sem, como na
   spec); binárias/lógicas/`??` quebram **depois do operador** (o parser começa um novo
   statement quando a linha começa com operador); condicional quebra depois do `if` e
   antes do `else`; lambda `fn(x) => expr` fica inline quando cabe; `match` é sempre
   multiline; C-style `for (;;)` é reconstruído a partir da AST dessugarizada.
5. **Linhas em branco:** exatamente uma entre declarações de topo (`class`, `fn`,
   `interface`, `enum`, `type alias`), métodos de classe e de interface; `val`/`var` de
   topo contam como statements (preservam ≤ 1 do autor, como qualquer statement); campos
   e statements preservam no máximo uma linha do autor; nenhuma depois de `{`/antes de
   `}`. Imports: zero dentro do grupo, uma entre `std.*` e locais, sem reordenar.
6. **Comentários:** comentário de linha normaliza `# `; `///` e `/* */` ficam verbatim
   (sem reflow); comentário força o grupo que o contém a quebrar. O printer mantém um
   cursor de fonte e drena a trivia de cada gap; nenhum comentário pode ser perdido ou
   duplicado. Trailing comments consecutivos no mesmo indent são alinhados quando a
   linha alinhada ainda cabe (regra estrita: grupos consecutivos, sem linha em branco).
7. **Sem mudança semântica:** o output é reparseado e comparado pelo `AstPrinter`
   (identificadores, operadores, literais, tipos e estrutura; spans/trivia/presença de
   token opcional ficam de fora). O oráculo congela os bytes do `format_source`.
8. **Uma engine, sem fallback.** O v1 é removido; `format_source` é a engine v2. Não há
   `--legacy`; o estilo antigo não é uma opção de configuração.
9. **Edits estruturados** (`--diff`, `--check --edits=json`, LSP) usam um diff determinístico
   por linhas sobre o mesmo core; range/selection continua em #110.

## Consequências

### Positivas

- Uma forma canônica de fato: o reflow, a linha em branco e o comentário seguem a mesma
  árvore, então `fmt(fmt(x)) == fmt(x)` vale no corpus inteiro.
- Comentários deixam de depender de heurística de linha; o attachment do ADR-0134 é
  exercitado pelo printer (incluindo listas, params, blocos vazios e `match`).
- O mesmo core serve CLI, LSP e (depois) MCP, sem uma segunda implementação.
- A AST e o checker não mudam; o formatter continua sendo tooling, não semântica.

### Negativas / custos

- **Churn:** a primeira execução muda 178 dos 320 arquivos parseáveis do oráculo; a
  aplicação ao repositório é um PR `chore/reformat` separado.
- **Custo:** formatar o corpus (349 arquivos, 320 parseáveis) passou de ~690 ms (v1) para
  ~1,27 s na primeira entrega e ~0,97 s depois do #152 (mediana de 5,
  `make frontend-bench`, 2026-11-23). O #152 trocou o `SourceIndex` completo por starts
  memoizados: o printer só precisa do offset de início, não de ends/merges. É ferramenta
  offline; não é gate de CI, mas a baseline de `docs/tech/arquitetura.md` é atualizada junto.
- O autor perde o controle de quebras manuais; só comentário e linha em branco (≤ 1)
  sobrevivem como intenção.
- Comentários em posições incomuns (entre `for (;;)` e a condição, por exemplo) podem
  andar para o slot canônico mais próximo; o texto nunca muda, a posição relativa pode.
- C-style `for` é reconstruído por padrão da AST dessugarizada; um `for` sem incremento
  e um `while` equivalente produzem a mesma árvore, então a reconstrução depende da
  forma exata do Block sintético.
- A regra de operador no fim da linha é uma restrição do parser, não uma preferência
  estética: o estilo “operador no começo” exigiria mudar a gramática.

### Neutras

- Formatação não afeta I1/I4; o teste de equivalência é de AST, não de execução.
- O formatter Lox (self-host) continua dependendo do parser self-hosted (ADR-0124) e
  passa a ter um alvo de bytes mais exigente: o Doc IR é a referência de paridade.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Reflow por stream de tokens | Preserva comentário de graça, mas não expressa lambda/ternário inline, agrupamento de binárias e trailing comma condicional; dois mecanismos de layout. |
| Híbrido: Doc IR só em listas/chamadas | Statements continuariam sem wrapping e a idempotência entre construtos ficaria frágil; mais código a longo prazo. |
| Continuar com heurística de linha | É o status quo que a issue #109 quer substituir; comentário continua sem dono. |
| Operador no início da continuação | Inválido: o parser trata uma linha começando com operador como novo statement (testado). |
| Flag `--legacy`/config por projeto | ADR-0092 já fixou um perfil canônico; duplicar engines dobra a manutenção e fragmenta o estilo. |
| Range formatting nesta tranche | Depende de edits por range e fica em #110, junto com a superfície MCP. |

## Como verificar

- `uv run pytest tests/test_formatter_doc.py tests/test_formatter_v2.py tests/test_formatter.py tests/test_formatter_edits.py`
  — Doc IR, golden fixtures, corpus (idempotência, AST igual, comentários), CLI e edits.
- `make oracle` — a seção `fmt` do manifesto é o contrato de bytes; `make oracle-update`
  só depois de revisar o diff.
- `make frontend-bench` — custo de parse+format e pico de memória.
- `make check-fast` — ruff, mypy strict e a suíte sem backend.
- Critério para revisitar: um construto que não caiba em nenhuma forma válida, um
  comentário que não possa ser anexado sem mudar o texto, ou a paridade Lox exigir uma
  representação de Doc diferente.

## Referências

- [`docs/guia-estilo.md`](../guia-estilo.md) — norma humana de formatação.
- [`docs/spec/sintaxe.md`](../spec/sintaxe.md) — trailing comma e formas opcionais.
- [`docs/tech/arquitetura.md`](../tech/arquitetura.md) — mapa de módulos e baseline.
- gofmt/rustfmt/prettier — formatter canônico, sem config, idempotente.
