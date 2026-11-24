# ADR-0140 — `match` com padrões literais

- **Status:** accepted (implementado em 2026-11-23)
- **Data:** 2026-11-23
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0041](0041-enums-match.md) (enums/`match`),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (orçamento),
  [ADR-0014](0014-identidade-e-invariantes.md) (portão),
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `loxia_core/frontend/{expr,parser,ast_printer}.py`,
  `loxia_core/semantics/checker.py`, `loxia_core/execution/interpreter.py`,
  `loxia_core/backend/lower_enums.py`, `loxia/formatter/printer.py`,
  `tests/cases/match_literals.lx`, `tests/cases/errors/match_literal_float.lx`

## Contexto

O `match` do [ADR-0041](0041-enums-match.md) só aceita enum: `Color.Green`,
`Shape.Circle(r)` e `_`. Para `Int`, `String` ou `Bool`, o código volta a `if`/`elif` ou a
uma cadeia de `==`; para `nil`, volta a `if (x == nil)`. Isso não é só açúcar: uma cadeia
de `if` não tem a checagem de arm inalcançável e não expressa a intenção de “casar este
valor, senão o próximo”.

A v1 do ADR-0041 listou padrões literais como “em aberto”. Esta ADR fecha **apenas** esse
recorte; `match` estrutural (listas/mapas/tuplas), guards, `|`, ranges e `match` sobre
uniões/`Any` continuam fora.

## Decisão

Aceitar, no lugar de `pattern`, também:

```ebnf
pattern → INT | STRING | "true" | "false" | "nil" | "-" INT
        | "_"
        | IDENTIFIER "." IDENTIFIER ( "(" IDENTIFIER ( "," IDENTIFIER )* ")" )? ;
```

### Regras

- **Tipos do scrutinée:** `Int`, `String`, `Bool`, `Nil` ou um enum. `Any`, uniões e
  opcionais são recusados com “narrow it first”; a exaustividade de enum continua igual.
- **Sem mistura:** um `match` é ou todo de variantes de enum, ou todo de literais. Variante
  em match literal e literal em match de enum são erro de tipo.
- **Wildcard obrigatório fora de enum:** `Int`/`String`/`Bool`/`Nil` são abertos; sem `_` é
  `Non-exhaustive match; add a '_' arm.` (não há como enumerar todos os valores).
- **Sem `Float`:** `1.5` em padrão é erro de sintaxe dirigido; `Int` não promove para
  `Float` em padrão. `-1` é aceito (o sinal faz parte do literal).
- **Igualdade estrita:** `1` só casa `Int`, `true` só casa `Bool`, `nil` só casa `nil`.
  `1` e `true` não se misturam (ao contrário de `isinstance(True, int)` em Python).
- **Duplicata:** o mesmo literal duas vezes é `Unreachable match arm.`; qualquer arm depois de
  `_` também.
- **Tipo do resultado:** união dos tipos dos braços, como no match de enum.
- **Runtime:** se o checker for contornado, um match sem braço é `No match arm matched.`;
  a igualdade usa o mesmo modelo de `Int`/`String`/`Bool`/`nil` da linguagem.

### Orçamento e forma canônica

- Nenhuma keyword nova, nenhum nível de precedência novo e nenhuma forma de statement nova;
  `match` já existe. O teto de keywords continua 29 e o de statements 12.
- Uma grafia por conceito: literal direto no padrão (`0`, `-1`, `"x"`, `true`, `nil`), sem
  `case`, sem `when` e sem guard. `_` é o único curinga.
- O `match` continua **sem fallthrough** e sem `break`; isso é intencional e não muda.

### Backend

- O lowering escolhe o caminho literal quando **não há** `VariantPattern` (isso cobre
  `match` só com `_`, inclusive sobre enum); com variante, usa o caminho de enum existente.
- Literais `Int`/`Bool` comparam com `icmp`; `String` usa `lox_str_equal`; `nil` exige
  scrutinee `NIL` e casa sem valor (um `nil` em scrutinee não-`Nil` é erro explícito, não
  `true` silencioso). O resultado é o mesmo phi/união do match de enum.
- Sem regra de tipo nova: o checker é a fonte; o backend não infere.

## Consequências

- **Positivas:** `match` vira útil para valores simples sem perder a exaustividade de enum;
  remove cadeias de `if`/`==`; o caminho de literal é pequeno e testável no backend.
- **Negativas:** dois modos no mesmo `match` (enum e literal), com regras de exaustividade
  diferentes; a mensagem “add a '_' arm” é a única saída para tipos abertos.
- Sem mudança em runtime C, ABI, GC ou memória.

## Alternativas rejeitadas

| Alternativa | Por quê |
| --- | --- |
| Só `Int` | `String`/`Bool`/`nil` são o mesmo custo e os casos mais comuns. |
| Exaustividade de `Bool` sem `_` | Dois valores ainda deixam o tipo aberto para o checker; exigir `_` mantém a regra única. |
| `Float` | Igualdade de ponto flutuante em padrão é armadilha (NaN, `-0.0`); fica fora. |
| Misturar enum e literal | Torna a exaustividade ambígua e o backend mais complexo sem dor demonstrada. |
| Guards/`|`/ranges | É `match` estrutural/avançado, não este recorte. |
| `switch`/`case` | Segunda grafia; o `match` existente já é expressão. |

## Como verificar

- `tests/cases/match_literals.lx`: `Int`, `String`, `Bool`, `nil`, negativo, wildcard e
  wildcard-only sobre enum; diferencial `l6`. O `-0` do formatter é coberto em
  `tests/test_formatter_v2.py`.
- `tests/cases/errors/match_literal_float.lx`: erro dirigido para `Float`, exit 65.
- `tests/test_checker.py::test_literal_match` e `test_literal_match_errors`: sucesso,
  não-exaustivo, tipo errado, duplicata e mistura enum/literal.
- `tests/test_formatter_v2.py`: padrões literais round-trip.
- `make check` verde (backend incluído).
