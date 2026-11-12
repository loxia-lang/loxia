# ADR-0028 — Overflow checado no modo `--debug`

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0006](0006-int-float-separados.md),
  [ADR-0012](0012-comentarios-divisao-potencia-bits.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [ADR-0026](0026-freeze-1.0.md),
  [`../../TIPOS.md`](../../TIPOS.md) §2, [`../spec/semantica.md`](../spec/semantica.md),
  [`../spec/erros.md`](../spec/erros.md)
- **Implementação:** [`src/numeric.py`](../../src/numeric.py),
  [`src/interpreter.py`](../../src/interpreter.py), [`lox/cli.py`](../../lox/cli.py),
  [`tests/test_numeric.py`](../../tests/test_numeric.py),
  [`tests/test_interpreter.py`](../../tests/test_interpreter.py),
  [`tests/test_cli.py`](../../tests/test_cli.py)

## Contexto

`Int` é i64 e o release faz **wrapping** de forma determinística
(`9223372036854775807 + 1` → `-9223372036854775808`). Isso é simples e rápido, mas esconde
bugs de overflow. O LLVM oferece `sadd.with.overflow`/`ssub.with.overflow`/
`smul.with.overflow`; o tree-walk precisa de um modo equivalente para continuar sendo o
oráculo dos testes diferenciais.

Havia ainda um detalhe independente: `INT_MIN // -1` e `INT_MIN % -1` são UB em
`sdiv`/`srem` do LLVM. O release já devolve `INT_MIN`/`0` (wrapping), então o backend
precisará de guarda mesmo sem o modo debug.

## Decisão

1. **`--debug` liga a checagem de overflow**; sem a flag, o comportamento release continua
   wrapping. `--debug` também vale no REPL.
2. Operações checadas: `+`, `-`, `*`, `**` (cada multiplicação intermediária), unary `-`,
   `INT_MIN // -1` e `INT_MIN % -1`.
3. Overflow gera **erro de runtime fatal** (`Integer overflow.`, exit 70), na linha do
   operador.
4. Shifts (`<<`, `>>`, `>>>`) continuam operações bitwise de 64 bits, sem checagem
   aritmética; `bit_not` também não checa.
5. O release mantém wrapping para `--debug` desligado. Para `INT_MIN // -1` e `% -1`, o
   backend release deve emitir guarda e devolver `INT_MIN`/`0`, nunca `sdiv`/`srem` UB.
6. A checagem fica no modelo numérico (`checked=True`), não no parser nem no checker. O
   checker continua aceitando a operação; a falha é de runtime.

## Consequências

- Debug fica mais lento, mas release não paga o custo.
- I1 continua verificável: o backend debug usa `*.with.overflow` e aborta; release usa
  `add`/`sub`/`mul` com wrap e as guardas de divisão.
- Testes diretos de `numeric` continuam no default wrapping; o modo checado é explícito.
- `math.abs(INT_MIN)` segue a mesma regra: erro no debug, `INT_MIN` no release (quando
  `math` entrar; ver ADR-0029).
- O erro é fatal, coerente com o freeze: não há exceção recuperável na 1.0.

## Alternativas rejeitadas

- **Sempre checado**: muda a semântica release e a performance; o modelo i64 wrapping já
  está fixado.
- **Sempre wrapping, sem debug**: mantém o status quo, mas deixa o LLVM `sdiv` UB e não
  oferece ferramenta de diagnóstico.
- **Checar no checker**: overflow depende de valores, não só de tipos; não é trabalho
  estático.
- **Checar shifts**: são operações de bits definidas modulo 2^64; chamar isso de overflow
  confunde o modelo.
