# ADR-0010 — Tipagem estática gradual (checker + `--check`)

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TODO.md`](../../TODO.md) §2/§11, [`../../TIPOS.md`](../../TIPOS.md),
  [`../spec/semantica.md`](../spec/semantica.md), [`../spec/sintaxe.md`](../spec/sintaxe.md)
- **Implementação:** `src/ty.py`, `src/checker.py`, `src/parser.py`, `src/stmt.py`,
  `src/token_type.py`, `src/scanner.py`, `lox/cli.py`; testes em `tests/test_checker.py`,
  `tests/test_cli.py`, `tests/cases/typed_functions.lox`

## Contexto

O interpretador é dinâmico e continuará sendo o oráculo. Para o LLVM, porém, tipos são
necessários: `i64`/`double` desboxados, offsets fixos de campo e checagem antes de gerar IR.
A decisão é ter uma linguagem **estaticamente tipada com inferência local**, sem obrigar o
`Int x = f()` de Java: funções declaram parâmetros e retorno; locais e expressões são
inferidos. A discussão está no histórico do `TODO.md` §2 e em `TIPOS.md`.

## Decisão

1. **Checker separado, depois do resolver**: `Scanner → Parser → Resolver → Checker →
   Interpreter`. Tipos são **apagados em runtime**; o tree-walk continua dinâmico.
2. **Modo `--check`**: valida tipos, não executa e retorna exit 65 em erro. Sem `--check`,
   o programa roda como antes (anotações são ignoradas pelo interpretador).
3. **Anotações obrigatórias nas funções** quando checadas: `fun f(a: Int, b: String = "x")
   -> Bool`. `init` não declara retorno. Métodos seguem a mesma regra.
4. **Inferência local**: `val x = f()` infere sem anotação; `var`/`val` sem inicializador
   exigem anotação quando checadas (`Can't infer type of 'x'; add an annotation.`).
5. **Sintaxe de tipos**: primitivos (`Int`, `Float`, `Bool`, `String`, `Nil`, `Any`,
   `Never`, `Range`), classes, `List[T]`, `Map[K, V]`, uniões `A | B` e `T?` como açúcar
   de `T | Nil`. Non-null por padrão: `Int` não aceita `nil`; `Int?` aceita.
6. **Promoção** só `Int → Float` na checagem; o sentido contrário exige cast explícito
   (ainda não implementado).
7. **Booleanos como no Python**: condições usam truthiness (qualquer tipo); `and`/`or`
   devolvem o operando e curto-circuitam; o checker calcula o tipo com
   `truthy(A) | B` / `falsy(A) | B`. `!` continua sendo a negação; a keyword `not` fica
   para depois (duas precedências diferentes seria armadilha).
8. **Corpo de expressão `= expr` fica adiado**; funções usam bloco `{ ... }` por enquanto.
9. **Sem narrowing de fluxo ainda**: `if x != nil { x + 1 }` ainda não promove `x` para
   `Int` (T5). Uniões são checadas na atribuição/passagem, não refinadas por `if`.
10. **Sem generics/funções de primeira classe no checker** ainda: `List`/`Map` são
    sintaxe válida, mas não há valores; tipos de função como valor ficam para P3.

## Consequências

### Positivas

- Base para LLVM: assinaturas conhecidas, campos e locals tipados, promoção explícita.
- Erros de tipo com linha/token antes de executar.
- Sem cerimônia em locais; sem `self`; sem `Int x = ...` redundante.
- `--check` é opt-in, então código dinâmico e golden cases continuam funcionando.

### Negativas / custos

- **Dois modos**: sem `--check` não há garantia de tipo; quem quiser segurança precisa
  rodar o checker.
- Sem narrowing, `Int?` exige checagem manual/`??` (P2) antes de usar como `Int`.
- Anotações de `Int → Float` são apagadas no tree-walk: `val f: Float = 1` checa, mas
  imprime `1` em runtime (o LLVM converteria). Documentado como limitação do oráculo.
- Sem `fun` genérica/traits; `List`/`Map` só entram de verdade com o checker T4/T6.
- Mensagens do checker são simples (`Expected Int, found String.`); spans/códigos ficam
  para o redesign de diagnósticos.

### Neutras

- Novos tokens `:`, `?`, `[`, `]`, `->`, `|`; `Ty` no `Param`/`Var`/`Field`/`Function`.
- `src/ty.py` (tipos e helpers de união) e `src/checker.py` separados do interpretador.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| HM completo com tudo inferido | mutação/`nil`/classes tornam mensagens e generalização caras; T3 fica como evolução |
| Tipar obrigatoriamente todos os programas | quebraria todo o código dinâmico/golden de uma vez; `--check` permite migração |
| Checar em runtime | não ajuda o LLVM e duplica regras; o tree-walk deve continuar simples |
| `:` para retorno (Kotlin) | `->` já era a sintaxe planejada e lê melhor em `fn` |
| `not` keyword agora | precedência diferente de `!`; duas negações confundem (fica para decidir) |

## Como verificar

- `tests/test_checker.py` (programa anotado limpo; erros de atribuição, chamada, aridade,
  tipo desconhecido, anotação ausente, campo, união/`nil`, iteração);
- `tests/test_cli.py` (`--check` não executa, exit 65, conflito com `--dump-ast`);
- `tests/cases/typed_functions.lox` (anotações não quebram a execução);
- `tests/test_parser.py` (anotações em parâmetro/retorno/campo, `T?`, `List[T]`);
- `make check`.

Critério para revisar: quando narrowing (T5), generics (T4), funções de primeira classe
ou o codegen LLVM entrarem; ou se `--check` passar a ser o modo padrão.
