# ADR-0019 — Interpolação `"${expr}"`

- **Status:** accepted
- **Data:** 2026-11-11
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0013](0013-ternario-nil-aware-escapes.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [`TIPOS.md`](../../TIPOS.md) §3
- **Implementação:** [`src/frontend/scanner.py`](../../src/frontend/scanner.py),
  [`src/frontend/parser.py`](../../src/frontend/parser.py), [`src/frontend/expr.py`](../../src/frontend/expr.py),
  [`src/execution/interpreter.py`](../../src/execution/interpreter.py), [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`tests/cases/interpolation.lox`](../../tests/cases/interpolation.lox)

## Contexto

Strings são imutáveis e o `+` exige duas strings. Montar mensagens com valores não-string
obriga a chamar `str` em cada pedaço:

```lox
print "fib(" + str(n) + ") = " + str(fib(n))
```

Isso é ruidoso e fácil de errar. A spec já listava interpolação como P2, e o Lox2 usa uma
forma parecida. A pergunta é a sintaxe (com prefixo `f`, sem prefixo, `$`, `\()`), o que
pode aparecer dentro e como converter o valor.

## Decisão

A string usa `"${expressão}"`:

```lox
print "fib(${n}) = ${fib(n)}"
print "mapa: ${{"a": 1}}"
print "escape: \${nome}"      # imprime ${nome} literal
print "cifrão: $5"            # $ sem { é literal
```

### Regras

- **Qualquer expressão** pode aparecer dentro de `${...}`: operadores, chamadas, índice,
  mapa, lista, condicional, outra string interpolada.
- A expressão é avaliada **da esquerda para a direita**, junto com os trechos de texto.
- O valor é convertido com a mesma `stringify` do `print`: `nil` → `nil`, `true`/`false`,
  `Int`/`Float`, listas/mapas no formato habitual; strings no topo saem sem quotes.
- `\${` produz `${` literal; `\$` produz `$`. Fora de `${...}`, `{`, `}` e `$` são
  literais.
- A string é um nó `InterpolatedString(parts)` com trechos `str` e expressões; o checker
  checa cada expressão e o tipo resultante é `String`.
- Interpolação aninhada (`"${"${nome}"}"`) é permitida; o scanner empacota cada expressão
  em um buffer de tokens próprio.
- Sem `f` prefix, sem `{{`/`}}`, sem format spec (`${x:.2f}`) na v1. `"""` e raw strings
  continuam fora.

### Scanner e parser

O scanner, ao encontrar `${`, escaneia a expressão em um buffer separado até o `}` de
fechamento (contando chaves internas de mapas, ignorando strings/comentários), e guarda os
tokens no literal do token `INTERPOLATED_STRING`. O parser cria um sub-parser para cada
buffer e monta o nó. Isso mantém a posição/linha dos tokens da expressão e permite
expressões arbitrárias sem `eval` nem string mágica em runtime.

## Consequências

### Positivas

- Mensagens legíveis sem `str()` repetido.
- Aproveita `stringify` e a ordem de inserção de listas/mapas; nada de formatação
  dependente de hash.
- Funciona com qualquer expressão e com aninhamento.
- O runtime não precisa interpretar texto: a AST já tem as subexpressões.

### Negativas / custos

- O scanner fica mais complexo (buffer de tokens, contagem de chaves, linhas).
- `\$` é um escape novo; `\$` fora de interpolação agora é válido em vez de erro.
- Sem format spec; alinhamento/decimais exigirão API futura.
- Interpolação de coleções pode surpreender (`"${[1, "a"]}"` imprime `[1, "a"]`); é a
  mesma regra do `print`.
- `"${}"` e `${` sem fechamento são erros de sintaxe, não valores.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `f"{expr}"` (Python) | Exige prefixo `f` e `{{`/`}}`; mais uma regra de string e conflito com o `f` de identificador. |
| `"{expr}"` sem prefixo | Toda chave literal precisaria de escape; surpreendente. |
| `"\(expr)"` (Swift) | Conflita com a tabela de escapes (`\(` vira caso novo) e é menos legível. |
| Só variáveis/campos/índice | Mais simples, mas não cobre `fib(n)` nem operadores. |
| Só `String` dentro de `${}` | Obriga `str()` em todo lugar e reduz o ganho. |
| Formatar em runtime com `eval` | Viola I2 e a separação scanner/parser; inaceitável. |

## Plano para o LLVM

Interpolação é açúcar: o codegen pode baixar `InterpolatedString` para concatenações de
strings e chamadas ao `stringify`/`str` do runtime, na mesma ordem da AST. Não há
dependência de hash, locale ou endereço; o resultado é determinístico.

## Como verificar

- Golden [`tests/cases/interpolation.lox`](../../tests/cases/interpolation.lox): texto,
  expressões, mapa/lista, `nil`, `bool`, escape, `$` literal, aninhamento e índice.
- Erros: `tests/cases/errors/interpolation_*.lox` (interpolação vazia, não terminada,
  variável indefinida).
- Checker: `tests/test_checker.py::test_interpolation_types_are_clean` e
  `test_interpolation_type_errors`.
- AST: `tests/test_ast_printer.py::test_dump_interpolated_string`.
- Determinismo: `interpolation.lox` em `tests/test_determinism.py`.
- `make check` verde.

## Referências

- [ADR-0013](0013-ternario-nil-aware-escapes.md) — escapes existentes.
- [ADR-0014](0014-identidade-e-invariantes.md) — I2/I3.
- Lox2 strings, JavaScript template literals e Python f-strings (comparação de sintaxe).
