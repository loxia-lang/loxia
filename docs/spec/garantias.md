# Garantias — o que a linguagem promete

Esta página é o **contrato** com quem usa a linguagem (ou escreve ferramenta em cima
dela). Não descreve sintaxe nem semântica — isso está em
[léxico](lexico.md), [sintaxe](sintaxe.md), [semântica](semantica.md) e
[erros](erros.md). Aqui ficam as promessas que sobrevivem a features novas.

A decisão por trás destas garantias (e o porquê de cada custo) está no
[ADR-0014](../adr/0014-identidade-e-invariantes.md).

## As três garantias

| # | Garantia | Status |
| --- | --- | --- |
| **I1** | Mesmo programa, mesmo resultado: o interpretador **é** a especificação | 🟡 L0–L5 + T7; corpus por nível anotado |
| **I2** | Nada acontece implicitamente | ✅ vale hoje |
| **I3** | Determinismo observável: mesma entrada ⇒ mesmos bytes | ✅ vale hoje e é testado em CI |

### I1 — Equivalência executável

O tree-walk é a **definição normativa** da linguagem. Todo programa do corpus declarado
tem que produzir o **mesmo stdout (bytes)**, o **mesmo stderr** e o **mesmo exit code**
nos dois motores; se divergirem, o bug é do backend.

O backend nativo cobre **L0–L5 + T7** ([ADR-0031](../adr/0031-backend-nativo.md),
[ADR-0046](../adr/0046-closures-celulas-l4.md), [ADR-0047](../adr/0047-optionais-escalares-l2-5.md)): `Int`, `Float`, `Bool`, `nil`, aritmética
com promoção `Int → Float`, `/` sempre `Float`, `%`, comparações, igualdade, `if`,
`while`, `val`/`var` com escopo e sombreamento, optionais escalares (`{i1, T}` e `nil`
contextual), classes/campos/métodos/`this`/`init`/herança/`super`, funções com `return`,
recursão e defaults,
ternário/`and`/`or`/`??` com curto-circuito, `String` (concatenação, igualdade, `len` em
code points, interpolação e `str`/`repr`) com arena, funções locais/lambdas, closures
(células e `env`) e valores de função (`<fn f>`/`<lambda>`). O teste diferencial
(`tests/test_backend.py`) compila cada caso, executa o binário e compara os três canais
com o interpretador — nunca com uma expectativa escrita à mão. O manifesto
`tests/corpus_manifest.py` declara os casos por nível.

O **corpus** é o corpus de conformidade inteiro, anotado: `tests/cases`, `exemplos/` e
`tests/official/cases`. A suíte do livro ainda é código cru do Crafting Interpreters
(`fun`, `//`, sem anotações) e por isso **não compila** enquanto não for anotada — a
anotação é pré-requisito do L1, e o I1 só vale para os programas efetivamente no corpus.
Não se escolhe o corpus depois olhando o que o backend já acerta.

Os níveis ainda não implementados rejeitam com **erro de compilação explícito** (exit 65),
nunca com lowering silencioso: classes/`T?` de referência (L5), `Any`/`List`/`Map`/
tuplas/enums (L6). No L4, função com defaults usada como valor também é rejeitada com 65
(fora do corpus declarado); ver [ADR-0046](../adr/0046-closures-celulas-l4.md).

A comparação é feita por canal: quando stdout e stderr vão para o **mesmo** descritor
(`2>&1`), a ordem de intercalação das duas saídas não faz parte da garantia.

Não existe promessa de que código interpretado e compilado tenham a mesma **velocidade**,
o mesmo consumo de memória ou o mesmo stack trace — só o mesmo resultado observável.
Recursão profunda fica fora do corpus até existir contador de pilha no runtime.

### I2 — Nada acontece implicitamente

Nenhuma conversão, coerção, truncamento, arredondamento, truthiness ou fallback acontece
sem estar escrito no código.

```lox
print 1 + 2.0      # 3.0  — promoção Int -> Float, só para cima
print 1 + "1"      # erro — sem coerção entre número e string
print 4 / 2        # 2.0  — `/` é sempre Float
print -7 // 2      # -3   — truncado
print 1 == 1.0     # true — igualdade numérica com promoção
print 1 == "1"     # false — tipos diferentes nunca são iguais
if ("") { print "vazio é truthy" }  # imprime: só nil e false são falsy
print (nil ?? 0)   # 0    — `??` troca apenas nil
print 3.9 as Int   # 3    — cast explícito, truncado
```

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
(`65` compilação, `70` runtime). Quando existir o formato estruturado, os códigos
(`E3xxx`…) também passam a ser estáveis.

## Princípios de design

Não são garantias testáveis como I1–I3: são os critérios que orientam as decisões de
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
- Os golden cases em `tests/cases/` fixam as recusas de I2 (coerção mista, `nil`
  surpresa, divisão por zero).
- Quando o backend existir: um teste diferencial rodando o mesmo corpus nos dois motores
  (I1).

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

## Revisitar

Se alguma garantia se mostrar impossível para uma feature, isso **não** se resolve
afrouxando o texto em silêncio: um ADR novo diz o que deixa de valer e por quê
(ver [ADR-0014](../adr/0014-identidade-e-invariantes.md), "Como verificar").
