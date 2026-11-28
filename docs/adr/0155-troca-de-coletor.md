# ADR-0155 — Troca de coletor: o invariante que mantém o GC local ao runtime (emenda ao ADR-0074)

- **Status:** accepted
- **Data:** 2026-11-27
- **Decisores:** Cássio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) (Boehm e contrato de
  memória), [ADR-0087](0087-heap-cap-e-self-hosting.md) (cap e self-hosting),
  [ADR-0046](0046-closures-celulas-l4.md) (células), [ADR-0149](0149-motores-primarios-thir-e-congelamento.md)
  (motores), [ADR-0154](0154-fronteira-do-thir.md) (fronteira do THIR)
- **Implementação:** [`runtime/core.c`](../../runtime/core.c) (`lox_alloc*`, `lox_init`),
  [`runtime/lox_runtime.h`](../../runtime/lox_runtime.h),
  [`tests/test_backend_memory.py`](../../tests/test_backend_memory.py)

## Contexto

O [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) fixou o Boehm conservador como coletor e
o `lox_alloc` como ponto de alocação. Com a F2 chegando, a pergunta prática é: quando trocarmos
de coletor (ou de modo do Boehm), quanto do compilador precisa mudar?

O estado atual já é melhor do que a pergunta sugere. `loxia_core/` não chama `malloc`,
`calloc`, `realloc`, `free` nem `GC_*`: o lowering emite chamadas a seis wrappers
(`lox_alloc`, `lox_alloc_atomic`, `lox_alloc_cell`, `lox_alloc_env`, `lox_alloc_closure`,
`lox_alloc_bytes`) e toda a configuração do Boehm vive em `lox_init` (interior pointers,
`GC_INIT`, cap de heap, `warn_proc`, `oom_fn`). Trocar Boehm por arena, refcount ou outro
tracing GC é reescrever a alocação de `runtime/core.c` mantendo a ABI; trocar o **modo** é
mexer em `lox_init`.

O que **não** é local é o que ninguém escreveu: o motivo de “não tem nada a fazer no codegen”
é o coletor ser **conservador** e a alocação ser **não-tipada**. Um coletor preciso ou
refcount precisa saber, em cada bloco, onde estão os ponteiros, e onde estão as raízes — e
essas duas informações hoje são implícitas (varredura da pilha e dos globais).

## Decisão

O contrato de memória passa a ter três cláusulas explícitas. Enquanto **todas** valerem, a
troca de coletor é local ao runtime:

1. **Alocação é não-tipada.** Todo bloco de heap vem de `lox_alloc*` com tamanho em bytes; o
   coletor não recebe o tipo do objeto. É o que o Boehm conservador quer e o que permite
   trocar de coletor sem tocar em cada `store`.
2. **Ninguém libera.** Não existe `free` na linguagem, no runtime nem no lowering; a
   reciclagem é do coletor.
3. **Toda referência viva é alcançável** de: globais, slots de pilha (varridos
   conservadoramente) e o grafo de células/`env`/instâncias. Nenhum motor pode guardar
   referência só num registrador ou num valor SSA fora do alcance dessa varredura.

Quebrar qualquer cláusula **não é refactor**: exige ADR novo, mapa de raízes no lowering
(`lox_root`/shadow stack) e, na cláusula 1, uma ABI de alocação tipada
(`lox_alloc_kind(kind, size)`).

`alloca` **não** faz parte deste contrato: é slot de pilha em LLVM, sem relação com o
coletor. `alloca` de tamanho constante é *static* e ganha offset fixo de frame mesmo dentro de
laço (verificado com 20 milhões de iterações em `while` com `var` no corpo); um adaptador
sobre `alloca` não compraria nada que o `-O2` (SROA/mem2reg) já não faça.

## Consequências

### Positivas

- A pergunta “e se trocarmos o GC?” tem resposta de uma linha: `runtime/core.c`.
- O lowering fica proibido de inventar alocação — a ABI é auditável por grep/teste.
- A fronteira do THIR ([ADR-0154](0154-fronteira-do-thir.md)) cria o lugar natural
  (`_slot`, binding → slot) onde um futuro mapa de raízes entraria, se a cláusula 3 cair.

### Negativas / custos

- Alocação não-tipada impede um coletor preciso “de graça”: quem quiser precisão paga a ABI
  tipada e o mapa de raízes.
- O teste de contrato olha strings no backend, não o comportamento do coletor; um `malloc`
  escondido atrás de outra camada não seria pego (o runtime C é auditado à parte).

### Neutras

- O cap de heap e o `Out of memory.` continuam como no ADR-0087; nada muda no observável.
- `lox_alloc_bytes` continua sendo “bytes”, não “instância de classe”: o coletor não precisa
  saber, o layout é do lowering.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Criar agora uma camada de abstração de memória (shim sobre `alloca`/alocação) | Não há dor: seis wrappers, zero `malloc`, zero bug de placement. Camada especulativa vira ruído em todo `store`. |
| ABI tipada desde já (`lox_alloc_kind`) | O Boehm conservador não usa a informação; seria custo em todos os sítios para um coletor que não existe. |
| Trocar Boehm por refcount para simplificar | Refcount precisa de contagem em cada célula/closure e não resolve ciclos; o ADR-0074 já rejeitou. |
| Esconder `alloca` atrás de um adapter | O `-O2` já promove slot para SSA quando o `alloca` está no bloco de entrada; o adapter só adicionaria indireção. |

## Como verificar

- `tests/test_backend_memory.py`: o backend não referencia `malloc`/`calloc`/`realloc`/`free`
  nem `GC_*`, e os seis wrappers existem no header do runtime.
- `make test-backend`: o corpus diferencial continua verde (I1) depois de qualquer mudança no
  runtime de memória.
- Critério para revisitar: um coletor preciso/refcount entrar em pauta; ou um motor guardar
  referência fora das raízes (bug de I1/I3, não de performance).

## Referências

- [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) — Boehm, `lox_alloc`, OOM.
- [ADR-0087](0087-heap-cap-e-self-hosting.md) — cap de 512 MiB e `--max-heap`.
- [`runtime/core.c`](../../runtime/core.c) — `lox_init` e os wrappers.
