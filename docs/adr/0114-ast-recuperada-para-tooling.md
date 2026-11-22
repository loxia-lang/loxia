> **Atualização (2026-11-22):** o [ADR-0132](0132-nos-de-erro-na-arvore-recuperada.md)
> adiciona `ErrorStmt`/`ErrorExpr` inertes e `ast --file-only --allow-errors`; a recuperação
> deixa de ser só prefixo. O texto abaixo é o registro histórico da decisão de 2026-11-19.

# ADR-0114 — AST recuperada para tooling (LSP)

- **Status:** accepted (implementado em 2026-11-19)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (LSP), [ADR-0075](0075-diagnosticos-estruturados.md)
  (diagnóstico), [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  issue [#46](https://github.com/loxia-lang/loxia/issues/46)
- **Implementação:** `loxia_core/frontend/parser.py` (recuperação em fronteira de
  declaração, já existente), `loxia/engine.py` (`last_recovered_statements`),
  `loxia/lsp.py` (`_diagnostics`/`_resolve_recovered`) e `tests/test_lsp_navigation.py`.

## Contexto

O parser do Loxia já recupera erros de sintaxe **em fronteira de declaração**: `_declaration`
captura `ParseError`, chama `_synchronize` e devolve `None`, então `parse()` termina com os
statements anteriores íntegros e `reporter.had_error` ligado. Mas o engine descartava esse
resultado (`last_statements = None` quando `had_error`) e o LSP indexava uma lista vazia —
enquanto o usuário digita, um erro no fim do arquivo apagava hover, definition e completion
do arquivo inteiro. O pyrefly parte do princípio oposto: o servidor continua útil com código
quebrado.

Ao mesmo tempo, `run`/`--check` precisam continuar estritos: erro de sintaxe é exit 65 e o
I1 compara stdout/stderr/exit code. Uma AST “mais tolerante” não pode vazar para o caminho
normativo.

## Decisão

1. **A recuperação existente é a única tolerância.** Não há parser alternativo nem modo
   “recuperar tudo”: o que sobrevive é o prefixo de declarações completas antes do erro. A
   declaração que falhou (e o resto do arquivo) fica de fora.
2. **O engine publica, não consome.** `Loxia.last_recovered_statements` expõe os statements
   recuperados depois do parse, mesmo com `had_error`. `last_statements` continua `None` no
   erro, e `run`/`check`/`build` seguem o caminho estrito de sempre.
3. **Só tooling lê o campo.** O LSP monta o `SymbolIndex` da AST recuperada com
   `checker=None` (nada de inferência) e roda o `Resolver` com um `ErrorReporter` próprio,
   só para recuperar escopos/referências. Erros do resolver na AST parcial nunca viram
   diagnóstico publicado.
4. **Contrato de consistência.** Os statements recuperados pertencem ao mesmo snapshot de
   texto do documento; nunca são misturados com o índice de outra versão. Documento fechado
   limpa o índice como hoje.
5. **Tipos não são prometidos.** Hover/definition mostram assinatura, doc e anotações
   explícitas; não há tipo inferido, narrowing nem erro de tipo na região recuperada.

## Consequências

### Positivas

- Hover, completion, definition e documentSymbol continuam funcionando no prefixo enquanto
  o usuário digita; o erro de sintaxe continua visível e correto.
- Zero mudança no CLI, no I1 ou no contrato de `--check`; a recuperação já era testada pelo
  parser.
- Reusa `Resolver.references` em vez de inventar resolução de símbolos para tooling.

### Negativas / custos

- Recuperação em granularidade de declaração: um erro dentro de uma função derruba a função
  inteira, não só a expressão quebrada.
- Sem checker não há tipo inferido no prefixo recuperado; hover pode ser mais pobre do que
  no arquivo válido.
- O `Resolver` roda uma segunda vez (com reporter descartável) no caminho de erro; medir se
  arquivos grandes com erro ficam lentos.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| AST last-known-good | Posições deslocam e as respostas apontam para o texto errado. |
| Parser totalmente tolerante (nós de erro, como Roslyn) | Muito maior; exige nó novo, visitor, checker e formatter; não é pré-requisito para o ganho. |
| Indexar o prefixo sem resolver | Definition em uso não funcionaria; o resolver separado é barato. |
| Deixar como estava | O editor perde tudo a cada erro de digitação; foi a motivação da issue #46. |

## Como verificar

- `tests/test_lsp_navigation.py::test_lsp_features_survive_syntax_error` — erro no fim do
  arquivo, hover/definition no prefixo.
- `uv run pytest tests/test_lsp.py` — diagnósticos e paridade com
  `check --error-format=json` continuam verdes.
- `make check-fast`; nenhum caminho de `run`/`check` lê `last_recovered_statements`.
