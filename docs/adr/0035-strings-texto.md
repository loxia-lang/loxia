# ADR-0035 — Strings e texto: acesso, ordem, identificadores e parse

- **Atualizado por:** [ADR-0071](0071-primitivas-de-runtime.md) (cache de code points e novas primitivas).
- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0007](0007-ranges-e-iteracao.md), [ADR-0016](0016-api-stdlib-hibrida.md),
  [ADR-0019](0019-interpolacao.md), [ADR-0026](0026-freeze-1.0.md),
  [ADR-0029](0029-conversoes-math.md), [ADR-0031](0031-backend-nativo.md),
  [`../spec/semantica.md`](../spec/semantica.md), [`../spec/semantica.md`](../spec/semantica.md),
  [`../spec/lexico.md`](../spec/lexico.md)
- **Implementação:** [`loxia_core/execution/natives/chars.py`](../../loxia_core/execution/natives/chars.py),
  [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py),
  [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py),
  [`loxia_core/backend/lower.py`](../../loxia_core/backend/lower.py),
  [`runtime/strings.c`](../../runtime/strings.c),
  [`tests/test_checker.py`](../../tests/test_checker.py),
  [`tests/test_backend.py`](../../tests/test_backend.py)

## Contexto

O §3 do `TIPOS.md` ainda listava decisões abertas sobre texto — e uma delas estava
**errada na doc**: dizia que `String` tinha "comparação léxica `<`", mas o interpretador
rejeitava com `Operands must be numbers.`. As decisões pendentes eram: acesso a caractere
(`s[i]`), ordenação, identificadores Unicode, normalização e o contrato de parse.

## Decisões

### 1. Acesso a caractere: `chars(s)`, não `s[i]`

`chars(s) -> List[String]` devolve os **code points** da string, cada um como `String` de
um code point. `s[i]` em string **continua erro** (`Only lists and maps can be indexed.`).

Motivo: em UTF-8, `s[i]` por code point é **O(n)**. Esconder isso atrás da sintaxe de
índice transforma `for i in 0..len(s) { s[i] }` em O(n²) sem o usuário ver. `chars`
explicita a conversão uma vez; a indexação de `List[String]` é O(1) e `for c in s`
continua lazy (não aloca lista). Sem tipo `Char`: cada elemento é `String` de 1 cp.

### 2. Ordenação: `< <= > >=` por code point

`String` compara com `<`, `<=`, `>`, `>=` na ordem de **code point**, que para UTF-8 válido
coincide com a ordem de bytes. `""` é menor que qualquer string não vazia; prefixo menor
vem antes. `==`/`!=` continuam por conteúdo. Misturar string e número é erro
(`Operands must be numbers.`), sem coerção. No backend, `lox_str_compare` (memcmp com
desempate por comprimento).

### 3. Identificadores continuam ASCII

`[A-Za-z_][A-Za-z0-9_]*`, sem normalização. Unicode é permitido em strings e comentários,
não em identificadores. Motivos: o freeze do ADR-0026, o custo de confusáveis
(latim/cirílico) e o tooling; não há dor que pague a superfície. `função` continua não
sendo identificador válido.

### 4. Sem normalização de strings

Strings são sequências de code points **byte-exatas**: `"é" != "e\u{301}"`, e `len` conta
code points (não grafemas). Normalizar (NFC ou similar) na criação seria uma transformação
implícita do dado do usuário, contra o I2; a comparação por code point é determinística
(I3).

### 5. Parse estrito; `String.to_int` não existe

`Int.parse`/`Float.parse` devolvem `T?`, aceitam sinal (`-42`, `+42`) e expoente (Float),
e rejeitam espaço, underscore e vazio (`nil`). Não há `String.to_int` nem `trim` implícito.

### 6. Sem builtins de string neste lote

`contains`, `startsWith`, `endsWith`, `indexOf`, `substring`, `split` e `trim` **não**
entram agora: são stdlib, não semântica de string, e o lote fecha o que o §3 listava.
`chars` é a exceção porque resolve o acesso a caractere.

## Consequências

- `chars("aço")` → `["a", "ç", "o"]`; `len(chars(s)) == len(s)`; `for c in s` continua
  iterando sem alocar.
- Comparações de string funcionam no interpretador **e** no backend (L3).
- `chars` depende de `List`, então o backend só a aceita no L6; até lá o erro é explícito
  (65 "not supported by the backend yet"), nunca lowering silencioso.
- Grafemas (UAX #29) ficam fora: `len("e\u{301}") == 2` e `chars` devolve 2 elementos.
- Documentação corrigida: a promessa falsa de `<` virou comportamento real.

## Alternativas rejeitadas

- **`s[i]` direto:** O(n) escondido; erro de performance silencioso.
- **Tipo `Char`:** superfície nova para um valor que já é `String` de 1 cp.
- **`char_at(s, i)`:** O(n) explícito, mas repetido a cada acesso; `chars` paga uma vez.
- **Normalização NFC:** transforma dado do usuário implicitamente.
- **Identificadores Unicode:** confusáveis e tooling; sem dor concreta.
- **`compare(s, t)` em vez de operadores:** menos ergonômico; `<` já é polimórfico para
  números e a ordem de string é bem definida.
- **Trim no parse:** transforma entrada silenciosamente; `nil` é explícito.
