# ADR-0059 — I4: check limpo compila, e promoção `Int → Float` só na aritmética

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0006](0006-int-float-separados.md),
  [ADR-0010](0010-tipagem-estatica.md), [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0024](0024-mutacao-monomorfica.md), [`../../TODO.md`](../../TODO.md) §2
- **Implementação:** [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py)
  (`_assignable`, `_mismatch_message`), [`tests/test_checker.py`](../../tests/test_checker.py),
  [`tests/test_backend.py`](../../tests/test_backend.py)

## Contexto

O contrato do [ADR-0014](0014-identidade-e-invariantes.md) promete que o interpretador é a
especificação e que os dois motores concordam. Uma varredura manual encontrou um programa
**com `--check` limpo** em que eles não concordam:

```lox
var x: Float = 1.5
x = 2
print x
```

| Canal | Antes |
| --- | --- |
| tree-walk | imprime `2`, exit 0 |
| `--check` | exit 0 (limpo) |
| `--emit=exe` | exit 65 — `Can't use INT where FLOAT is expected.` |

A causa é dupla e nenhuma das duas é aceitável:

1. O checker tratava `Int → Float` como atribuível em **qualquer** contexto
   (`_assignable` tinha `actual is INT and expected is FLOAT → True`), inclusive
   declaração, atribuição, argumento, default e `return`.
2. O backend tem a **sua própria** regra de coerção de slot (`lower_optionals.py`), que
   exige o tipo exato. Duas fontes de verdade para a mesma pergunta — exatamente o que o
   `AGENTS.md` §9 proíbe.

O mesmo furo aparecia em `return 2` numa função `-> Float`, em `f(2)` para parâmetro
`Float` e em `fn f(x: Float = 1)`. A declaração `val y: Float = 2` era pior: não falhava,
mas o slot era `Float` e o valor em runtime era `Int` (a anotação não converte, por
erasure), o que deixa o tipo declarado e o valor real em desacordo silencioso.

## Decisão

**Duas regras, uma fonte de verdade.**

### 1. Promoção só na aritmética

`Int → Float` continua valendo **apenas como regra de operandos aritméticos** — é o que o
[ADR-0006](0006-int-float-separados.md) decidiu (`1 + 2.0 → 3.0`, `1 == 1.0 → true`,
`1 < 2.5`). Em **contexto de armazenamento** ela é rejeitada, como em Kotlin:

| Contexto | Exemplo | Agora |
| --- | --- | --- |
| inicializador anotado | `val y: Float = 2` | erro |
| atribuição | `x = 2` (x `Float`) | erro |
| campo/índice | `this.x = 2`, `xs[0] = 2` | erro |
| argumento e default | `f(2)`, `fn f(x: Float = 1)` | erro |
| retorno | `return 2` (em `-> Float`) | erro |

A mensagem ensina a saída explícita:

```
Expected Float, found Int. Write `2.0` or use `2 as Float`.
```

`2 as Float` é conversão explícita (ADR-0029) e continua válida em runtime. A aritmética
não mudou: `1 + 2.0`, `4 / 2`, `1 == 1.0` e `2 ** 0.5` seguem iguais.

### 2. I4 — `--check` limpo ⇒ compila

Todo programa que passa no `--check` deve compilar, e a **única** recusa aceitável no
lowering é a lacuna já declarada e classificada:

```
... is not supported by the backend yet.
```

Qualquer outro erro depois de um check limpo é violação do I4 — significa que o backend
introduziu uma regra de tipo que o checker não conhece. O checker é a fonte de verdade;
o backend consome `type_of`/`storage_types` e não decide tipos por conta própria.

O I4 é o corolário operacional do I1: sem ele, "mesmo programa, mesmo resultado" pode
falhar *antes* de executar, e o usuário recebe dois diagnósticos contraditórios.

## Consequências

### Positivas

- Some a classe de divergência "check verde, emit vermelho" — e a mensagem é a mesma nos
  dois caminhos, porque a decisão é uma só.
- Some o desacordo silencioso de `val y: Float = 2` (slot `Float`, valor `Int`): agora é
  erro de tipo, não um valor que se comporta como `Int` num binding `Float`.
- O erro ensina a correção (`2.0` / `as Float`) em vez de exigir dedução.
- Fecha o buraco com um **gate sistêmico**: o corpus inteiro é varrido e nenhum caso com
  check limpo pode falhar por tipo no lowering (`test_i4_...`).
- Reforça I2 ("nada acontece implicitamente") no ponto exato onde ele era mais frágil.

### Negativas / custos

- **Mais verboso.** `val x: Float = 1`, `math.sqrt(9)` e `media(2)` deixam de ser aceitos;
  é preciso escrever `1.0`, `9.0`, `2.0`. É o preço explícito do I2.
- **Quebra compatibilidade de fonte.** Programas que dependiam da promoção implícita
  passam a falhar no `--check`. Como o `--check` é opt-in, o interpretador ainda os roda —
  mas aí eles não estão no corpus e o I1 não promete nada sobre eles. O corpus e os
  testes do checker foram tornados explícitos no mesmo commit.
- **Descoberta de novos casos.** Qualquer outra regra de tipo que viva só no backend
  (coerção de slot, união, `Any`) tende a aparecer no mesmo gate; é bom, mas cada
  aparição exige uma decisão (mover para o checker ou declarar lacuna).

### Neutras

- `as Float` continua sendo a conversão explícita; nada muda em runtime.
- Genéricos, `Any` e uniões não foram tocados: `_assignable` mantém a recursão estrutural,
  só perdeu a promoção numérica.
- Kotlin permite que literais inteiros caibam em `Byte`/`Short` por faixa; não fazemos
  isso com `Float` (seria coerção implícita de novo).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Backend converte `Int` para `Float` no slot | O tree-walk imprimiria `2` e o binário `2.0` — divergência silenciosa, pior que o erro. Converter também no tree-walk faria a anotação mudar o runtime, contra o erasure do [ADR-0010](0010-tipagem-estatica.md). |
| Rejeitar só na atribuição | Deixa `return 2`, `f(2)` e defaults divergindo; o furo volta por outro caminho. |
| Manter permissivo e registrar como divergência conhecida | Contradiz o I1 e o I4: "check limpo" viraria uma promessa sem conteúdo. |
| Emitir warning em vez de erro | Warning em CI é ruído que ninguém lê; e o programa continuaria divergindo. |
| Promoção explícita via `x = Float(2)` (construtor) | `Float` é namespace nativo reservado (não classe); `as Float` já cobre. |

## Como verificar

- [`tests/test_checker.py`](../../tests/test_checker.py):
  `test_int_float_promotion_is_rejected_outside_arithmetic` (oito contextos),
  `test_arithmetic_promotion_still_works`, `test_explicit_conversion_is_the_escape_hatch`.
- [`tests/test_backend.py`](../../tests/test_backend.py):
  `test_promocao_int_para_float_e_recusada_pelos_dois` (regressão do furo original) e
  `test_i4_check_limpo_nunca_vira_erro_de_tipo_no_lowering` (varredura do corpus).
- O gate roda em `make check` (pytest) e exige `--extra llvm` no CI.

**Gatilhos para revisitar:** se a sintaxe ganhar sufixo de literal (`2.0f`, `2d`) ou
conversão literal contextual; se o `--check` passar a ser o modo padrão (aí a promoção
implícita seria erro em todo programa, inclusive no REPL); se um caso de uso real mostrar
que a verbosidade do `2.0` dói mais que o I2 vale.
