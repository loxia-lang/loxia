# ADR-0134 — Trivia como side table do scanner

- **Status:** accepted (implementado em 2026-11-22)
- **Data:** 2026-11-22
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0092](0092-estilo-e-formatter.md) (formatter), [ADR-0129](0129-oraculo-do-front-end.md)
  (oráculo), [ADR-0132](0132-nos-de-erro-na-arvore-recuperada.md) (AST recuperada),
  issue [#108](https://github.com/loxia-lang/loxia/issues/108)
- **Implementação:** `loxia_core/frontend/trivia.py`, `loxia_core/frontend/scanner.py`,
  `loxia/engine.py` (`last_trivia`), `tests/test_trivia.py`

## Contexto

O formatter preserva comentários por heurística de linha e não consegue responder a
perguntas estruturais: qual comentário pertence ao campo/arm seguinte, quantas linhas em
branco existem dentro de um bloco, como quebrar uma chamada sem deixar um comentário
órfão. O scanner descarta `#`, `///` e `/* */`; a AST não tem como reconstruir a fonte.

A decisão de arquitetura já estava no tracker (#108): usar uma side table em vez de um
segundo lexer, tokens de trivia no stream principal ou uma CST completa.

## Decisão

1. **O scanner continua sendo o único lexer.** `scan_tokens()` devolve exatamente a mesma
   lista de tokens para o parser; em paralelo grava `Trivia` (whitespace, newline, line
   comment, block comment, doc comment) com `kind`, texto exato e `Span`. Bytes de erro
   léxico que não viram token (ex.: `!`, inteiro grande, string não terminada) entram como
   `other`, para que nenhum byte do texto normalizado fique sem dono.
2. **Side table, não AST aumentada.** Nenhum nó ganha campos de comentário; o AST, o
   checker, o interpreter e o backend não mudam.
3. **Round-trip normalizado.** `render(tokens, trivia, source)` reconstrói o texto
   normalizado (LF) byte a byte e falha se houver gap ou sobreposição; o fallback para
   `source` não pode esconder uma trivia que deixou de ser gravada. CRLF é normalizado pelo engine antes do scanner; o
   contrato é sobre o texto normalizado, não o arquivo cru.
4. **Attachment determinístico.** `TriviaTable` responde `leading`, `trailing`, `between`,
   `comments_before`, `comments_after` e `blank_lines_before`. Regra: comentário em linha
   própria pertence ao próximo nó; comentário trailing na mesma linha pertence ao nó
   anterior; uma linha em branco quebra a ligação.
5. **Doc comments não são duplicados.** `///` continua alimentando `Token.doc` e também
   aparece na trivia; o formatter pode escolher a representação, mas não perde o texto.
6. **Interpolação não vaza trivia.** Dentro de `${...}` os espaços já fazem parte do lexeme
   da string; o scanner suprime a gravação de trivia nesse trecho.

## Consequências

### Positivas

- Formatter/LSP podem preservar e mover comentários sem uma segunda lexer.
- O AST permanece enxuto e os hashes atuais não mudam; a trivia é opt-in para quem consome.
- O round-trip é uma prova barata e forte contra perda de bytes.

### Negativas / custos

- Mais memória no scanner: uma entrada por whitespace (o corpus tem muitos).
- Anexação de comentário é heurística: casos ambíguos (comentário entre dois nós na mesma
  linha, comentário no fim de bloco) precisam de regra documentada e testes.
- O formatter ainda precisa de um `Doc` IR (#109); a trivia sozinha não formata.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Trivia no stream principal, filtrada pelo parser | Todo consumidor do parser precisa tolerar tokens extras; blast radius grande. |
| CST lossless separada | Duas fontes de verdade e uma reescrita; a side table resolve o caso do formatter. |
| Campos de comentário em cada nó da AST | Infla o contrato e mistura sintaxe com apresentação. |
| Só heurística de linha no formatter | É o status quo que motivou a issue. |
