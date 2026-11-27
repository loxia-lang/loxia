# ADR-0132 — Nós de erro na árvore recuperada

- **Status:** accepted (implementado em 2026-11-22)
- **Data:** 2026-11-22
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0114](0114-ast-recuperada-para-tooling.md) (recuperação para
  tooling), [ADR-0129](0129-oraculo-do-front-end.md) (oráculo), [ADR-0014](0014-identidade-e-invariantes.md)
  (I1–I4), issue [#105](https://github.com/loxia-lang/loxia/issues/105)
- **Implementação:** `loxia_core/frontend/expr.py` (`ErrorExpr`),
  `loxia_core/frontend/stmt.py` (`ErrorStmt`), `loxia_core/frontend/parser.py`
  (recuperação e `_synchronize`), `loxia/engine.py` (`parse_file(allow_errors=...)`),
  `loxia/cli_args.py`/`loxia/cli_commands.py` (`--allow-errors`) e
  `tests/test_parser_recovery.py`

## Contexto

O [ADR-0114](0114-ast-recuperada-para-tooling.md) adotou recuperação em fronteira de
declaração: o parser sincronizava, descartava a declaração que falhou e o LSP recebia só o
prefixo íntegro. Isso mantém `run`/`check` estritos, mas apaga do editor justamente a
declaração em que o usuário está digitando; um erro dentro de uma função derruba a função
inteira.

A issue #105 pede nós de erro explícitos e recuperação mais fina. A decisão do ADR-0114 de
não ter “parser totalmente tolerante” continua válida: não queremos uma gramática
error-tolerant completa. O que muda é admitir nós de erro **inertes** na árvore recuperada,
com span, para que a ferramenta consiga continuar.

## Decisão

1. **Nós explícitos e inertes.** `ErrorStmt` e `ErrorExpr` carregam `start`/`end` (tokens) e
   a mensagem do parser. Eles nunca são executados, checados ou baixados; visitor de
   resolver/checker os ignora, o interpreter levanta erro se alguém tentar executá-los.
2. **Recuperação onde o editor precisa.** `_declaration` devolve `ErrorStmt` em vez de
   `None`; `_expression_statement` devolve `Expression(ErrorExpr(...))` para uma expressão
   quebrada. `_synchronize` para em `;`, em um statement starter e na mudança de linha,
   para não engolir o resto do arquivo.
3. **Estrito por padrão.** `run`, `check` e `build` continuam rejeitando qualquer árvore com
   erro (exit 65). O engine só devolve a árvore recuperada quando
   `parse_file(allow_errors=True)` é chamado.
4. **CLI opt-in e explícito.** `loxia ast --file-only --allow-errors` emite a árvore
   recuperada (S-expression ou JSON) e ainda sai 65; sem a flag, o comportamento estrito
   do ADR-0114 permanece. `--allow-errors` exige `--file-only`.
5. **Tooling consome, I1 não.** O LSP usa `last_recovered_statements` como antes, agora com
   nós de erro; `last_statements` continua `None` no erro e o caminho normativo não lê a
   árvore recuperada.
6. **Contrato de schema.** O JSON v1 serializava os nós genericamente; o v2 (#107) define
   `error_expr`/`error_stmt` com `$defs` e campos obrigatórios.

## Consequências

### Positivas

- O editor mantém símbolos e navegação dentro da declaração que falhou, não só no prefixo.
- O CLI ganha uma forma explícita de depurar a recuperação sem tornar `ast` tolerante por
  padrão.
- A AST recuperada passa a ter um contrato observável (`kind`, `span`, `message`), em vez de
  ser um detalhe interno do LSP.

### Negativas / custos

- Mais um par de nós e métodos de visitor em todos os visitors; qualquer visitor novo
  precisa decidir o que faz com erro.
- A recuperação ainda não reconstrói uma assinatura parcial: um erro em parâmetros pode
  derrubar a função inteira. O refinamento fica para um follow-up se doer.
- `--allow-errors` produz saída mesmo com exit 65; scripts precisam checar o código de saída.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter só o prefixo do ADR-0114 | É o problema: a declaração em edição some. |
| Parser totalmente tolerante (Roslyn) | Custo e gramática muito maiores; não é pré-requisito. |
| Nós de erro executáveis/checáveis | Violaria I1/I4 e mascararia programa inválido. |
| `--allow-errors` implícito no LSP e invisível no CLI | Não dá para testar/depurar a recuperação fora do editor. |

## Como verificar

- `tests/test_parser_recovery.py` — declaração, bloco e expressão; CLI com/sem
  `--allow-errors`.
- `tests/test_lsp.py`/`tests/test_lsp_navigation.py` — navegação em código quebrado.
- `make check-fast`; `run`/`check` continuam exit 65.
