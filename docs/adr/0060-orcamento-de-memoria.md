# ADR-0060 — Orçamento de memória faz parte do contrato (arena de 64 MiB)

- **Status:** superseded by [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0031](0031-backend-nativo.md), [ADR-0051](0051-l6-range-for-in-escalares.md),
  [`../../docs/spec/garantias.md`](../spec/garantias.md), [`../../TODO.md`](../../TODO.md) §6.5
- **Implementação:** [`runtime/runtime.c`](../../runtime/runtime.c) (`LOX_HEAP_BYTES`,
  `lox_alloc`), [`tests/test_backend.py`](../../tests/test_backend.py)
  (`test_orcamento_de_memoria_...`)

> **Substituído em 2026-11-14:** a arena de 64 MiB foi trocada pelo GC Boehm. O novo
> contrato é hard cap de 128 MiB e I1 até 64 MiB de memória viva
> ([ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md)). O texto abaixo fica como
> histórico da decisão que valeu até o M7.

## Contexto

O I1 promete "mesmo programa, mesmo resultado" entre interpretador e binário. O backend
aloca em uma **arena de 64 MiB, sem `free`** (`LOX_HEAP_BYTES` em `runtime/runtime.c`),
enquanto o tree-walk roda sobre o GC do Python, sem teto explícito.

Consequência: um programa que aloca em laço (concatenar strings, `push` em lista, criar
tuplas) roda no interpretador e **morre** no binário:

```
[line 0] Out of memory.
```

Isso é uma divergência **observável** (stdout vs panic), não uma diferença de "consumo de
memória" como a que o contrato já admitia. Ela nunca esteve declarada em
[`garantias.md`](../spec/garantias.md) — só a recursão profunda estava. Com o L6 trazendo
`List`/`Map`/tuplas boxeadas, alocar em laço deixou de ser exótico: o furo cresce a cada
container.

O [TODO](../../TODO.md) §6.5 já prevê GC (Boehm) no M7. A pergunta que este ADR fecha é
**o que se promete enquanto o GC não existe**, e como a promessa muda quando ele chegar.

## Decisão

**O orçamento de memória é parte do I1, declarado e testado.**

1. **Teto determinístico no backend:** 64 MiB de arena, sem `free`. Exceder é falha
   determinística: `exit 70`, stderr `[line 0] Out of memory.`, sem traceback e sem
   depender da máquina, do SO ou de variável de ambiente. O mesmo binário, no mesmo
   programa, falha sempre no mesmo ponto.
2. **I1 vale para programas que caibam no orçamento.** Programas que alocam acima de
   64 MiB estão **fora do corpus do I1 por definição** — a divergência ali é o
   comportamento declarado, não um bug. O corpus (e qualquer caso novo) deve caber no
   orçamento; o teste do limite documenta a fronteira.
3. **A assimetria é explícita:** o interpretador pode rodar programas que o binário
   recusa. Isso não é escondido: `garantias.md` diz que o tree-walk não tem teto e que o
   I1 não cobre programas acima do orçamento.
4. **O teto não é configurável por ambiente.** Um `LOX_HEAP_BYTES` por env faria o
   resultado depender de onde o binário roda, quebrando I3. Se um dia for configurável,
   será uma flag de build declarada no contrato, não um detalhe do ambiente.
5. **GC futuro (M7):** quando o Boehm entrar, a arena é substituída por heap coletado e
   este ADR é **substituído** por outro que responda: qual é a falha determinística de
   esgotamento de memória (se houver), e como o corpus do I1 continua válido. O que
   **não** muda é o princípio: limite de recurso é contrato, não surpresa.
6. **Ownership estilo Rust: rejeitado.** Empréstimo/borrow em tempo de compilação exige
   um sistema de tipos de regiões que não existe, conflita com closures, classes e
   `Any` dinâmico, e — o mais importante — não pode ser verificado pelo tree-walk, que é
   o oráculo. O caminho do projeto é GC (Boehm), como já registrado no TODO §6.5.

## Consequências

### Positivas

- O furo deixa de ser surpresa: quem compila um programa que aloca muito sabe o que
  esperar, e falha cedo com mensagem determinística.
- O corpus do I1 ganha uma condição de escopo **verificável**, não uma vaga promessa de
  "programas pequenos".
- O teste do limite vira a documentação executável do orçamento: se alguém mudar
  `LOX_HEAP_BYTES`, o teste quebra e obriga a atualizar o contrato.
- Prepara a chegada do GC: quando ele entrar, a decisão a tomar está nomeada (o que passa
  a ser a falha de esgotamento?) em vez de ser descoberta em produção.

### Negativas / custos

- **Arena sem `free` desperdiça.** Toda alocação intermediária (concatenação, `push`,
  `s+1` em laço) fica até o fim do processo. Programas "razoáveis" podem morrer cedo; o
  orçamento de 64 MiB é apertado para processamento de texto.
- **Falha no meio do programa.** Não há unwind nem `try` para "out of memory": o processo
  aborta com 70. Programas que querem tratar o caso não têm como.
- **`[line 0]`.** O panic de memória não sabe a linha corrente (a alocação não recebe a
  linha); o diagnóstico é menos útil que os demais. Fica registrado como limitação até o
  runtime de GC, que terá o mesmo problema salvo se a linha for passada em cada alocação.
- **Mais um item no contrato para manter.** Se a arena mudar de tamanho ou de estratégia,
  ADR + `garantias.md` + teste mudam juntos.

### Neutras

- O tree-walk não ganha limite artificial: impor um teto no interpretador tornaria o
  oráculo menos capaz que o produto e criaria divergência ao contrário.
- Benchmarks não medem memória hoje; não é requisito deste ADR.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Declarar só "programas pequenos" e não medir | Não é verificável; volta a ser promessa sem conteúdo, o problema que o ADR-0014 combate. |
| Fazer o backend usar `malloc`/`free` + GC agora | Escopo do M7 (Boehm); antecipar GC para tapar buraco de contrato inverte a ordem do projeto. |
| Limitar o tree-walk ao mesmo teto | O interpretador é o oráculo; limitá-lo esconde programas que a linguagem aceita e cria divergência ao contrário. |
| Ownership/borrow estilo Rust | Incompatível com closures/classes/`Any` e não verificável pelo tree-walk; exigiria reescrever a linguagem. |
| Teto configurável por env | Resultado passaria a depender do ambiente — quebra I3. |
| Ignorar e considerar bug de backend | É comportamento determinístico por design; sem declarar, o I1 mente. |

## Como verificar

- [`tests/test_backend.py`](../../tests/test_backend.py),
  `test_orcamento_de_memoria_e_deterministico_no_backend`: um programa que dobra uma
  string até passar de 64 MiB **roda** no interpretador (exit 0) e **falha** no binário
  (exit 70, `Out of memory.`), duas vezes seguidas com o mesmo stderr — a falha é
  determinística, não flaky.
- `docs/spec/garantias.md` §"Orçamento de memória" — a versão para quem usa.
- `make check` roda o teste (com `--extra llvm` no CI).

**Gatilhos para revisitar:** quando o Boehm entrar (M7), quando L7 medir memória, se um
programa legítimo do corpus encostar no teto, ou se `Line 0` começar a atrapalhar a
depuração de verdade.
