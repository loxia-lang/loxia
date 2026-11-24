# ADR-0139 — `break` e `continue` sem rótulos

- **Status:** accepted (implementado em 2026-11-23)
- **Data:** 2026-11-23
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0066](0066-orcamento-e-gate-sintatico.md) (orçamento),
  [ADR-0138](0138-remocao-for-c-style.md) (remoção do `for` C-style),
  [ADR-0014](0014-identidade-e-invariantes.md) (portão),
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `loxia_core/frontend/{token_type,keywords,stmt,parser,ast_printer}.py`,
  `loxia_core/semantics/resolver.py`, `loxia_core/execution/interpreter.py`,
  `loxia_core/backend/{lower,lower_range,lower_base}.py`, `loxia/formatter/printer.py`,
  `tests/cases/break_continue.lx`, `tests/cases/errors/{break,continue}_outside_loop.lx`

## Contexto

`while` e `for-in` existem desde cedo, mas não há saída antecipada nem “próxima
iteração”. O código paga com flags (`done`, `finished`, `found` em `std/proc`, `std/csv`,
`std/property`) ou com `return` dentro de uma função. No top level, `for (;;)`/`while
(true)` só termina com `raise`/erro.

O C-style `for` foi removido antes desta slice ([ADR-0138](0138-remocao-for-c-style.md)).
Isso elimina o caso mais difícil de `continue` (executar o update) e deixa apenas dois
laços, ambos com alvo de continuação natural:

- `while`: recheca a condição;
- `for-in`: avança o iterador e mantém o binding `val` por iteração.

A linguagem já reserva `async`/`await` sem sintaxe; `break`/`continue` são keywords novas.
O teto de keywords do [ADR-0066](0066-orcamento-e-gate-sintatico.md) sobe de 27 para 29;
o de formas de statement chega a 12 (o teto).

## Decisão

Adicionar as formas:

```ebnf
breakStmt    → "break" terminator ;
continueStmt → "continue" terminator ;
```

Sem rótulos (`break outer`), sem valor (`break 1`) e sem `loop {}`.

### Semântica

- `break` sai do laço **mais interno**; `continue` inicia a próxima iteração.
- `while`: `continue` volta à condição.
- `for-in`: `continue` avança o iterador; o binding é `val` e uma nova `Environment` é
  criada por iteração, como hoje.
- `try/finally`: sair por `break`/`continue` executa o `finally` antes do salto. Se o
  `finally` também sair (`break`, `continue`, `return` ou `raise`), a saída dele vence.
- **Fronteira de função/lambda:** `break`/`continue` não atravessam função nem lambda; o
  resolver zera a profundidade de laço ao entrar em qualquer função. Fora de laço é erro
  de compilação `E2010` (`Can't use 'break' outside of a loop.` /
  `Can't use 'continue' outside of a loop.`), exit 65.
- `break`/`continue` dentro de `if`, `match`, `try` ou bloco continuam mirando o laço
  lexical que os contém.
- Não há `break` de `match`/`switch`: `match` é expressão sem fallthrough e não precisa
  disso.

### Orçamento e forma canônica

- `break` e `continue` são **palavras reservadas**, não keywords contextuais. A
  alternativa contextual manteria o teto em 27, mas permitiria variáveis chamadas
  `break`/`continue` e um parser dependente do próximo token; o ganho não paga a
  ambiguidade.
- Uma grafia por conceito: `break` para sair, `continue` para a próxima iteração. Nada de
  `stop`/`next`/`skip` como aliases.
- O teto de keywords passa a 29 e o de formas de statement a 12; uma próxima forma de
  statement exige revisão do orçamento.

### Backend

- O lowering mantém uma pilha de `LoopContext` com `break_block`, `continue_block` e a
  profundidade de `try` na entrada do laço.
- `break`/`continue` emitem, antes do salto, o `finally` dos `try` abertos **dentro** do
  laço (e só deles), depois fazem `br` para o alvo. `while` aponta `continue` para o bloco
  de condição; `for-in` aponta para o bloco de avanço.
- Sem regra de tipo nova: o checker não inventa tipos; o resolver valida o contexto. I4
  permanece.

## Consequências

- **Positivas:** loops com saída antecipada deixam de precisar de flags; `while (true)` e
  `for-in` ganham o idioma padrão de `break`/`continue`; o backend ganha um contexto de
  laço reutilizável para futuros `loop`/rótulos, se um dia existirem.
- **Negativas:** +2 keywords e +2 formas de statement (teto atingido); código que usava
  `break`/`continue` como identificadores deixa de compilar (migração: renomear).
  `finally` + `break`/`continue` exige testes específicos nos dois motores.
- Nenhuma mudança no runtime de valores, no GC ou na ABI.

## Alternativas rejeitadas

| Alternativa | Por quê |
| --- | --- |
| Flags/`return` | Já é o workaround; piora legibilidade e não funciona no top level. |
| `stop`/`next`, `halt`/`skip` | Segunda grafia/identidade; `next` colide com `next()` de iterador. |
| Rótulos agora | Aumenta parser/resolver/backend sem dor demonstrada; fica para depois, se houver. |
| Keywords contextuais | Evita o orçamento, mas permite `break` como variável e torna o parser sensível ao contexto. |
| `break` com valor | Não há uso; `return`/`raise` cobrem. |
| `loop {}` | Duplica `while (true)`; continua não-objetivo (ADR-0066). |
| Implementar só `break` | `continue` é o par natural; deixar um só é pior que ambos. |

## Como verificar

- `tests/cases/break_continue.lx`: `for-in`, `while`, `try/finally`, laço aninhado.
- `tests/cases/errors/{break,continue}_outside_loop.lx` e `break_in_lambda.lx`: exit 65 e
  mensagem estável.
- `tests/test_parser.py`: AST de `break`/`continue`; o golden `break_continue.lx` cobre o
  caminho do interpreter.
- Diferencial do corpus `l2` (`break_continue.lx`) nos três canais; `make check` verde.
- `tests/test_docs_consistency.py::test_scoreboard_de_keywords_bate_com_keywords` confere
  o teto de 29.
