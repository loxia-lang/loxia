---
sources:
  - tests/corpus_manifest.py
  - tests/test_backend.py
  - tests/test_determinism.py
  - src/backend/**
  - runtime/runtime.c
  - src/semantics/checker.py
---

# Garantias — o que a linguagem promete

Esta página é o **contrato** com quem usa a linguagem (ou escreve ferramenta em cima
dela). Não descreve sintaxe nem semântica — isso está em
[léxico](lexico.md), [sintaxe](sintaxe.md), [semântica](semantica.md) e
[erros](erros.md). Aqui ficam as promessas que sobrevivem a features novas.

As decisões por trás destas garantias estão nos
[ADR-0014](../adr/0014-identidade-e-invariantes.md) (I1–I3),
[ADR-0059](../adr/0059-i4-check-limpo-compila.md) (I4) e
[ADR-0074](../adr/0074-gc-boehm-e-contrato-de-memoria.md) (memória; substitui o
[ADR-0060](../adr/0060-orcamento-de-memoria.md)).

## As quatro garantias

| # | Garantia | Status |
| --- | --- | --- |
| **I1** | Mesmo programa, mesmo resultado: o interpretador **é** a especificação | 🟡 cobre o corpus declarado (tabela abaixo) |
| **I2** | Nada acontece implicitamente | ✅ vale hoje |
| **I3** | Determinismo observável: mesma entrada ⇒ mesmos bytes | ✅ vale hoje e é testado em CI |
| **I4** | `--check` limpo ⇒ o backend compila (ou recusa só a lacuna declarada) | ✅ vale hoje e é testado em CI |

### I1 — Equivalência executável

O tree-walk é a **definição normativa** da linguagem. Todo programa do corpus declarado
tem que produzir o **mesmo stdout (bytes)**, o **mesmo stderr** e o **mesmo exit code**
nos dois motores; se divergirem, o bug é do backend.

O corpus é o corpus de conformidade inteiro, **anotado e classificado por nível** em
`tests/corpus_manifest.py`. Cada caso está em `LEVELS` (o backend compila e concorda),
`PENDING` (o `--check` passa, o backend ainda recusa com **65** e a mensagem
`... is not supported by the backend yet.`) ou `NEGATIVE` (falha de propósito no
`--check`). Um caso só entra em `LEVELS` quando os três canais batem; a promoção é
monotônica e o teste diferencial nunca compara com expectativa escrita à mão. A lista de
`PENDING` é pública: é o registro honesto do que falta, não um segredo.

<!-- levels:start -->
| Nível | Casos que compilam e concordam (I1) |
| --- | --- |
| `l0` | 4 |
| `l1` | 3 |
| `l2` | 14 |
| `l2.5` | 3 |
| `l3` | 14 |
| `l4` | 7 |
| `l5` | 25 |
| `l6` | 46 |
| `k0` | 2 |
| `t1` | 6 |
| `t7` | 2 |

**126 casos** em 11 níveis compilam e concordam; **0 em `PENDING`** (); **6 negativos** de propósito.
<!-- levels:end -->

Os níveis ainda não implementados rejeitam com **erro de compilação explícito**
(exit 65), nunca com lowering silencioso.

A comparação é feita por canal: quando stdout e stderr vão para o **mesmo** descritor
(`2>&1`), a ordem de intercalação das duas saídas não faz parte da garantia.

Não existe promessa de que código interpretado e compilado tenham a mesma **velocidade**,
o mesmo consumo de memória ou o mesmo stack trace — só o mesmo resultado observável.
Recursão profunda fica fora do corpus até existir contador de pilha no runtime.

#### Orçamento de memória ([ADR-0074](../adr/0074-gc-boehm-e-contrato-de-memoria.md))

O binário usa **GC Boehm** conservador, com **hard cap de 128 MiB** de heap coletado
(substitui a arena de 64 MiB do [ADR-0060](../adr/0060-orcamento-de-memoria.md)). Exceder
o cap é `exit 70` + `Out of memory.` no stderr, sem traceback, e o teto **não** depende do
ambiente.

- O **I1 cobre programas cujo pico de memória viva caiba em 64 MiB**. Acima disso, o
  programa está fora do corpus: pode rodar, mas não há garantia de resultado nem de ponto
  de falha.
- O interpretador **não** tem teto (GC do Python) e pode rodar programas que o binário
  recusa — a assimetria é declarada.
- Como o Boehm é conservador, o **ponto exato** em que um programa acima do cap estoura
  não é determinístico: roots falsos dependem da pilha e do ASLR. O que é estável é o
  canal, a mensagem e o exit code. Programas que imprimem antes de estourar não têm o
  prefixo de stdout coberto pelo I1.

### I2 — Nada acontece implicitamente

Nenhuma conversão, coerção, truncamento, arredondamento, truthiness ou fallback acontece
sem estar escrito no código.

```lox
print 1 + 2.0      # 3.0  — promoção Int -> Float, só em aritmética
print 1 + "1"      # erro — sem coerção entre número e string
print 4 / 2        # 2.0  — `/` é sempre Float
print -7 // 2      # -3   — truncado
print 1 == 1.0     # true — igualdade numérica com promoção
print 1 == "1"     # false — tipos diferentes nunca são iguais
if ("") { print "vazio é truthy" }  # imprime: só nil e false são falsy
print (nil ?? 0)   # 0    — `??` troca apenas nil
print 3.9 as Int   # 3    — cast explícito, truncado
```

Em **armazenamento** não há promoção: `val x: Float = 2`, `x = 2`, `f(2)` e `return 2` em
função `-> Float` são erros de tipo; escreva `2.0` ou `2 as Float`
([ADR-0059](../adr/0059-i4-check-limpo-compila.md)).

Se você quiser a conversão, ela é escrita: não há "o compilador resolve".

### I3 — Determinismo observável

Mesma entrada + mesmas flags ⇒ **mesmos bytes** de saída e de diagnóstico. Isso vale para
stdout, stderr, exit code e `--dump-ast`. Ficam proibidos na saída: endereço de memória,
PID, timestamp, caminho absoluto, ordem de `set`/`dict`, locale e ordem de diretório.

O prelúdio da 1.0 não lê o relógio nem outras entradas ambiente: `clock` foi removido
([ADR-0026](../adr/0026-freeze-1.0.md)). Um módulo `time` futuro, se existir, fica
explicitamente **fora** desta garantia e do corpus diferencial.

`math.*` implementado é determinístico: `abs`, `min`, `max`, `clamp`, `floor`, `ceil`,
`round`, `trunc` e `sqrt`. `log`, `exp`, `sin`, `cos`, `tan` e `pow` dependem da libm e
ficam **fora** da 1.0/I3 ([ADR-0029](../adr/0029-conversoes-math.md)). `--debug` muda o
comportamento de overflow por design; a garantia vale para as mesmas flags.

```bash
./lox programa.lox > a.txt 2>&1   # duas vezes, em máquinas/flags diferentes
./lox programa.lox > b.txt 2>&1
cmp a.txt b.txt                   # idênticos
```

A redação de uma mensagem de erro **pode mudar entre versões**; o exit code não
(`65` compilação, `70` runtime). Os **códigos** de diagnóstico são estáveis e nunca
reaproveitados ([ADR-0075](../adr/0075-diagnosticos-estruturados.md)); a saída é ordenada
por `(arquivo, offset, código)`, deduplicada, limitada por `--max-errors` e o caminho
exibido é sempre relativo. O JSON carrega `schema_version`.

### I4 — `--check` limpo ⇒ compila

Todo programa que passa no `--check` compila. A **única** recusa aceitável no lowering é a
lacuna já declarada e classificada:

```
... is not supported by the backend yet.
```

Qualquer outro erro depois de um check limpo é violação do I4. O checker é a **fonte de
verdade** dos tipos; o backend consome os tipos publicados e não inventa regra própria.

```bash
uv run main.py --check prog.lox      # exit 0 …
uv run main.py --emit=exe prog.lox   # … então isto compila (ou recusa só "not supported")
```

É o corolário operacional do I1: sem ele, o mesmo programa poderia dar `2` no
interpretador e um erro de tipo no compilador, com o usuário recebendo dois diagnósticos
contraditórios ([ADR-0059](../adr/0059-i4-check-limpo-compila.md)).

## Princípios de design

Não são garantias testáveis como I1–I4: são os critérios que orientam as decisões de
sintaxe, tipos e stdlib. O que ainda é aspiracional está marcado.

1. **Sem ruído** — `;` opcional, `elif`, corpo de uma linha; a sintaxe não deve exigir
   cerimônia para o caso comum.
2. **Expressões primeiro** — quase tudo produz valor; `if`/`match`/bloco como expressão
   ficou **fora da 1.0** ([ADR-0026](../adr/0026-freeze-1.0.md)); ternário e `??` cobrem o
   caso comum.
3. **Imutável por padrão** — `val`/`var` implementados; parâmetros são imutáveis e `var x`
   libera a mutação. Argumentos no [ADR-0005](../adr/0005-val-var-imutabilidade.md).
4. **Tipos opcionais, não cerimônia** — anotar só onde ajuda; no `--check` a inferência
   local já existe e parâmetros/retorno continuam assinados. Inferir parâmetro sem
   anotação ficou adiado; ver [ADR-0020](../adr/0020-assinaturas-explicitas.md).
5. **Falhar cedo e claro** — spans, caret e stack trace são P1; hoje há linha e mensagem.
6. **Previsível** — nada de coerção implícita, nada de `nil` surpresa; é o I2.
7. **Identidade = invariantes, não features** — o contrato é o
   [ADR-0014](../adr/0014-identidade-e-invariantes.md); toda feature passa pelo portão de
   admissão.

## Como isso é verificado

- [`tests/test_determinism.py`](../../tests/test_determinism.py) roda casos com
  `PYTHONHASHSEED` diferentes e exige igualdade byte a byte (I3), além de proibir dados
  voláteis.
- [`tests/test_backend.py`](../../tests/test_backend.py) compila cada caso do manifesto e
  compara stdout/stderr/exit com o interpretador (I1), varre o corpus exigindo que check
  limpo nunca vire erro de tipo (I4) e documenta o orçamento de memória.
- Os golden cases em `tests/cases/` fixam as recusas de I2 (coerção mista, `nil`
  surpresa, divisão por zero, promoção em armazenamento).
- `tests/test_docs_consistency.py` impede que esta página fique defasada em relação ao
  manifesto e ao CLI.

## O que **não** é prometido

- **Velocidade.** O tree-walk é o oráculo, não o produto final; benchmarks servem para
  detectar regressão, não para competir com Rust.
- **Redação de mensagem entre versões.** Só o exit code (e, no futuro, o código do
  diagnóstico) é estável.
- **Compatibilidade com o Lox do livro.** A linguagem divergiu de propósito
  (`val`/`var`, `Int`/`Float`, `class B(A)`); não há modo de compatibilidade.
- **Estabilidade de ABI, bytecode ou formato de objeto.** Não existem ainda, e quando
  existirem não serão contrato público na primeira versão.
- **Timing.** Nada promete quando um `nil`/objeto é liberado, nem ordem de finalização —
  justamente para não quebrar I1.
- **Programas acima do orçamento de memória** no binário (hard cap de 128 MiB e I1 até
  64 MiB de memória viva) e **recursão profunda** sem contador de pilha.

## Revisitar

Se alguma garantia se mostrar impossível para uma feature, isso **não** se resolve
afrouxando o texto em silêncio: um ADR novo diz o que deixa de valer e por quê
(ver [ADR-0014](../adr/0014-identidade-e-invariantes.md), "Como verificar").
