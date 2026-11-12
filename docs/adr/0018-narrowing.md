# ADR-0018 — Narrowing de fluxo para `T?`

- **Status:** accepted
- **Data:** 2026-11-11
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0013](0013-ternario-nil-aware-escapes.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [`TIPOS.md`](../../TIPOS.md) §2.2
- **Implementação:** [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

O checker já entende `T?` como `T | Nil`, mas não usa o fluxo para refinar a união. O
padrão mais comum com opcionais falha:

```lox
val nome: String? = "Ana"
if (nome != nil) {
  print len(nome)   # erro: String | Nil
}
```

O mesmo vale para `List[T]?` e `Map[K, V]?`, que só funcionam hoje com `??`, `or` ou `?.`.
Sem narrowing, o usuário precisa de casts/`Any` ou reescrever o código em volta da
expressão.

## Decisão

O checker refina variáveis **diretas** em `if`/`elif`/`else` e depois de retorno
antecipado:

```lox
if (nome != nil) { len(nome) }        # then: String
if (nome == nil) { ... } else { len(nome) }  # else: String

if (nome) { len(nome) }               # truthiness remove Nil

if (nome == nil) { return }
len(nome)                             # depois do if: String
```

### Escopo da v1

- Reconhece `x == nil`, `x != nil` (em qualquer lado), `if (x)` por truthiness e `!` em
  volta dessas formas, inclusive com parênteses.
- Refina **variáveis**, não `obj.campo` nem `xs[i]`.
- `val` e `var` estreitam. Atribuir à variável remove o refinamento ativo; a checagem da
  atribuição usa o tipo **declarado**, não o estreitado, então `var x: String?` aceita
  `x = nil` dentro de um `if (x != nil)`.
- Retorno antecipado:
  `if (x == nil) { return }` aplica o ramo oposto ao restante do bloco. Funciona com
  `else` e com blocos que sempre retornam.
- **Fora da v1:** `is T`, `while`, `and`/`or` de curto-circuito, refinamento de campos,
  merge completo de fluxo em CFG e aliasing. Ficam registrados no `TODO.md` §2.

### Mecânica

- `_narrowings` é uma pilha paralela aos escopos; cada entrada guarda
  `(índice_do_escopo_da_declaração, tipo_estreitado)`. Isso evita que um refinamento
  antigo se aplique a uma variável redefinida em escopo interno.
- `_refinements(expr, truth)` deriva um mapa `nome -> Ty` da condição; `_check_branch`
  empilha um nível temporário e `_always_returns` decide se o ramo oposto deve persistir.
- `_invalidate(nome)` remove o refinamento de todos os níveis ativos. É conservador: uma
  atribuição dentro de um ramo faz o resto do bloco perder o refinamento, mas nunca aceita
  um valor potencialmente `nil`.
- O runtime não muda; tipos continuam apagados.

## Consequências

### Positivas

- `T?` fica utilizável sem cast: `len(xs)`, `m[k]`, `xs.push` e chamadas de método dentro do
  `if`.
- O padrão `if (x == nil) { return }` funciona, que é o caso mais comum em funções.
- É checker-only: não custa nada no tree-walk nem cria promessa nova no LLVM.

### Negativas / custos

- `and`/`or` ainda não refinam; condições compostas continuam exigindo `if` aninhado.
- Loops não refinam; `while (x != nil)` não ajuda dentro do corpo.
- `is T` não existe; uniões que não sejam `T?` só melhoram com narrowing futuro.
- A invalidação é conservadora: atribuir em um ramo pode perder o refinamento no bloco
  inteiro.
- Refinar `var` é pragmático; closures que mutam a variável durante uma chamada não são
  rastreadas (documentado).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só `x == nil`/`x != nil`, sem truthiness/early return | Menor, mas não cobre `if (x)` nem o padrão de retorno antecipado. |
| Só `val` | Mais conservador, mas deixa `var x: T?` sem o ganho principal. |
| Incluir `is T` na v1 | Exige operador novo, semântica de tipo em runtime e mais superfície; fica para depois. |
| Fluxo completo com CFG/merge | Poderoso, mas desproporcional ao estágio atual; a v1 cobre o uso real. |
| Refinar `obj.campo`/`xs[i]` | Precisa rastrear expressões e mutação de objetos; fica para o narrowing completo. |

## Como verificar

- `tests/test_checker.py::test_narrowing_types_are_clean` (val/var, `List?`, `Map?`,
  `else`, truthiness, `elif`, early return).
- `tests/test_checker.py::test_narrowing_limitations` fixa o que ainda **não** funciona
  (`and`, `while`, `else` de `!= nil`).
- `make check` verde.

## Referências

- [ADR-0010](0010-tipagem-estatica.md) — checker gradual.
- [TIPOS.md](../../TIPOS.md) §5 — `T?` e non-null.
- Kotlin smart casts, TypeScript control-flow analysis e mypy narrowing — modelos mentais.
