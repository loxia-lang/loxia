# ADR-0068 — `not` substitui `!`

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0005](0005-val-var-imutabilidade.md),
  [ADR-0010](0010-tipagem-estatica.md), [ADR-0011](0011-fn-elif-ponto-e-virgula.md),
  [ADR-0032](0032-narrowing-campos-indices.md),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md)
- **Implementação:** `loxia_core/frontend/scanner.py`, `loxia_core/frontend/keywords.py`,
  `loxia_core/frontend/parser.py`, `loxia_core/semantics/checker.py`, `loxia_core/execution/interpreter.py`,
  `loxia_core/backend/lower.py`; casos `tests/cases/unary.lox`, `precedence.lox`,
  `bang_removed.lox`; testes em `tests/test_scanner.py`, `tests/test_parser.py` e
  `tests/test_checker.py`

## Contexto

A negação lógica era `!`, herdada do Lox do livro. O gate sintático
([ADR-0066](0066-orcamento-e-gate-sintatico.md)) já registrava `&&`/`||` como
não-objetivo porque `and`/`or` existem — mas a negação ficou simbólica, sozinha na
família de operadores de palavra. O próprio [ADR-0010](0010-tipagem-estatica.md) listava a
keyword `not` como alternativa adiada por um motivo específico: *duas* negações (`!` e
`not`) teriam precedências diferentes e confundiriam.

A análise de 2026-11-13 mostrou que o custo de migrar é pequeno e que o custo de esperar
cresce: `!` aparecia em **7** linhas de código Lox no repositório (duas golden cases e
duas linhas de teste), **zero** vezes na suíte oficial dos capítulos 10–13, e em um único
`case` do lowering. A `!=` é token próprio e não é afetada.

## Decisão

`not` **substitui** `!` como negação lógica, no mesmo nível de precedência (unário):

1. **`not` é palavra-chave** (`TokenType.NOT`), escaneada por `KEYWORDS`. Deixa de ser
   identificador.
2. **`!` sozinho vira erro dirigido** no scanner:
   `Unexpected character: ! (use 'not' for negation).` Nenhuma gramática nova; é o tipo de
   diagnóstico que o ADR-0066 §2 permite sem contar como feature.
3. **`!=` continua igual** (`TokenType.NOT_EQUAL`), agora com nome coerente com a
   negação. Não existe `not=`.
4. **Precedência idêntica ao `!`**: `not a == b` é `(not a) == b`, não `not (a == b)`.
   A tentação de copiar Python (`not` mais fraco que comparação) foi recusada: seria uma
   segunda regra de precedência para a mesma negação e quebraria a tradução mental de C.
5. **`not not x` é a forma de negar duas vezes**; `!!x` deixa de existir junto com `!`.

## Consequências

### Positivas

- `and`/`or`/`not` formam uma família coerente; o único operador de palavra que faltava
  era a negação.
- Uma grafia só: o gate não precisa de exceção. `!` não fica como alias (alias violaria
  "grafias por conceito = 1").
- Nenhuma regra de newline nova: `not` é prefixo, como `!` era. `not` no início de linha
  fora de brackets continua começando uma expressão/statement.
- Custo de migração hoje é de horas; depois de mais código e exemplos, seria maior.

### Negativas / custos

- Programa que usava `not` como identificador quebra. É uma quebra deliberada e barata
  agora (nenhum caso no repositório), caríssima depois.
- `not not x` é mais verboso que `!!x`.
- `--dump-ast` muda de `(! nil)` para `(not nil)`, e casos golden precisam acompanhar.
- A assimetria `not` (palavra) × `!=` (símbolo) permanece; é a mesma de Python e é
  documentada em [`../spec/lexico.md`](../spec/lexico.md).

### Neutras

- O nível de precedência continua 19; o orçamento de keywords sobe de 23 para 24 na
  contagem do ADR-0066 (que passou a explicitar o que conta: ver revisão do ADR).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter `!` | É a única negação simbólica numa família de operadores de palavra; o gate pediu coerência. |
| Aceitar `!` e `not` como alias | Duas grafias para o mesmo conceito — exatamente o que o ADR-0066 recusa (`fun`/`fn`, `?:`/`??`). |
| `not` com precedência de Python | Criaria duas regras de negação (uma para quem escreve `!`, outra para `not`); o ADR-0010 já apontava o risco. |
| Manter `!` e adicionar `not` para leitura | Mesmo problema do alias, com o agravante de precedências diferentes. |
| Só documentar `!` como "legado" | Um alias silencioso é pior que um erro dirigido; o diagnóstico ensina a forma canônica. |

## Como verificar

- `uv run python -m tests.runner bang_removed` (exit 65, mensagem dirigida);
- `uv run python -m tests.runner unary` e `precedence` (negação e precedência unária);
- `uv run pytest tests/test_scanner.py tests/test_parser.py tests/test_checker.py`;
- `--dump-ast` de `not nil` imprime `(not nil)`;
- `grep -rn 'BANG' loxia_core tests` não retorna nada;
- `make check` (docs consistency + suíte completa).

## Referências

- [ADR-0010](0010-tipagem-estatica.md) — alternativa `not` adiada por precedência.
- [ADR-0011](0011-fn-elif-ponto-e-virgula.md) — precedente de manter uma grafia só.
- [ADR-0066](0066-orcamento-e-gate-sintatico.md) — gate, orçamento e não-objetivos.
- [ADR-0067](0067-desambiguacao-sintatica.md) — diagnóstico dirigido não é sintaxe nova.
