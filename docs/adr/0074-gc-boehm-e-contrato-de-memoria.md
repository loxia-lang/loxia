# ADR-0074 — GC Boehm e contrato de memória (hard cap de 128 MiB)

> **Atualizado por** [ADR-0087](0087-heap-cap-e-self-hosting.md): o hard cap default
> passou a **512 MiB** e o build ganhou `--max-heap`; o Boehm, os roots e o I1 até 64 MiB
> live continuam valendo. O corpo abaixo é o registro histórico da decisão de 128 MiB.

- **Status:** accepted (implementado)
- **Data:** 2026-11-14
- **Decisores:** Cássio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  [ADR-0031](0031-backend-nativo.md) (backend e memória),
  [ADR-0046](0046-closures-celulas-l4.md) (closures/células),
  [ADR-0060](0060-orcamento-de-memoria.md) (**substituído** por este ADR),
  [ADR-0071](0071-primitivas-de-runtime.md) (kernel e cache de strings),
  [ADR-0037](0037-async-direcao.md) (frames e GC),
  [`../../TODO.md`](../../TODO.md) §9/§13, [`../spec/garantias.md`](../spec/garantias.md)
- **Implementação:** [`runtime/runtime.c`](../../runtime/runtime.c) (`lox_alloc`,
  `lox_init`, OOM), [`src/backend/driver.py`](../../src/backend/driver.py) (link,
  `mod.verify`), [`src/backend/llvm_ir.py`](../../src/backend/llvm_ir.py) (verificação),
  [`tests/test_backend.py`](../../tests/test_backend.py),
  [`tests/test_ir_verify.py`](../../tests/test_ir_verify.py)

## Contexto

O backend nativo aloca em uma arena de 64 MiB, sem `free`
([`runtime.c`](../../runtime/runtime.c)), com um único ponto bruto de alocação
(`lox_alloc`) e quatro wrappers (`cell`, `env`, `closure`, `bytes`). O L6 fechou e o
corpus declarado compila; a limitação que resta não é de linguagem, é de **memória**:
programas que alocam em laço (concatenar strings, `push` em lista, criar closures)
morrem em `Out of memory.` enquanto o tree-walk roda no GC do Python.

O [ADR-0060](0060-orcamento-de-memoria.md) declarou essa assimetria como contrato e já
previu este momento: o GC substituiria a arena e a falha de esgotamento seria redecidida.
O [ADR-0031](0031-backend-nativo.md) §7, o [ADR-0046](0046-closures-celulas-l4.md) §9 e o
[ADR-0037](0037-async-direcao.md) apontam Boehm como direção. O [ADR-0071](0071-primitivas-de-runtime.md)
mostra que a stdlib em Lox é inviável sem GC: `substr`/`join`/cache de `LoxStr` alocam, e
a arena sem `free` transforma qualquer parser/lexer em crescimento linear de memória.

Havia, portanto, três decisões acopladas: **qual coletor**, **qual contrato de memória**
e **quando** ele entra em relação ao kernel de primitivas. Este ADR fecha as três.

## Decisão

### 1. Boehm (`libgc`) é o coletor do backend

O `lox_alloc` passa a chamar `GC_malloc`; dados que não contêm ponteiros (bytes de
string, cache de offsets) usam `lox_alloc_atomic`. O interpretador continua sem
dependência de runtime; `--emit=ll` e `--emit=obj` não linkam `libgc`. Só `--emit=exe`
exige `libgc` (build), além de `llvmlite` e de um `cc`.

A fronteira `lox_alloc`/`lox_alloc_*` é preservada. Não há header de GC obrigatório, não
há mudança de ABI de classes, closures ou containers, e o lowering não é reescrito.

### 2. Roots: pilha conservadora, estáticos cobertos

O Boehm enxerga pilha e registradores; isso cobre locais, temporários e `longjmp` sem
shadow stack. Os pontos que o coletor precisa enxergar são cobertos assim:

- globais LLVM de topo (`g.<nome>`) e classes são roots pelo data segment que o Boehm
  escaneia; os testes cobrem o caso. Se uma plataforma não escanear o data segment, o
  fallback é `GC_add_roots` explícito;
- literais de string são estáticos; se o cache do [ADR-0071](0071-primitivas-de-runtime.md)
  for alocado no heap, ele precisa ser root (ou `GC_malloc_uncollectable` para literais);
- `LoxStr.data` é ponteiro interior se o layout continuar header+dados; o Boehm precisa
  aceitar ponteiros interiores, ou o layout é dividido em header + bloco atômico. A
  decisão fica na implementação, mas o teste de interior pointer é obrigatório;
- descritores, vtables, closures, envs, células, instâncias, listas, mapas, tuplas, enums
  e `LoxValue` já são objetos de heap e são cobertos pelo coletor conservador.

### 3. Contrato de memória: hard cap de 128 MiB, I1 até 64 MiB live

- O binário tem um **hard cap de 128 MiB** de heap coletado (`GC_set_max_heap_size`), não
  configurável por ambiente. Exceder é `exit 70` + `Out of memory.` no stderr, sem
  traceback.
- O **I1 cobre programas cujo pico de memória viva caiba em 64 MiB**. Acima disso, o
  programa está fora do corpus: pode rodar, mas não há garantia de resultado nem de ponto
  de falha. O número 64 MiB preserva a promessa antiga e deixa margem para o overhead do
  Boehm.
- Com coletor conservador, o **ponto exato** da falha de esgotamento não é determinístico
  (roots falsos dependem de pilha/ASLR). O que é estável é o canal, a mensagem e o exit
  code. Testes de OOM usam programas claramente acima do cap e não imprimem stdout antes
  da falha.
- O tree-walk continua **sem teto** (GC do Python). A assimetria é declarada, como no
  ADR-0060; o I1 vale dentro da margem acima.

### 4. O kernel v1 vem depois do GC

A ordem do [TODO §13.7](../../TODO.md) passa a ser: **GC** (este ADR) → 13.3 (cache,
`substr`, `join`, `charCodeAt`, `fromCodePoint`) → 13.4 (tabela única) → 13.2 (kernel de
SO). O 13.4 pode andar em paralelo; 13.3 e 13.2 tocam `LoxStr`, `main` e `runtime.c` e
não entram no mesmo commit do GC.

O cache de `LoxStr` do [ADR-0071](0071-primitivas-de-runtime.md) passa a ser alocado no
heap coletado, não na arena; a nota de atualização no ADR-0071 registra isso. Nada de FFI
genérica ou `ctypes` no oráculo.

### 5. `mod.verify()` é gate explícito do build

O driver verifica o módulo LLVM **antes** de emitir `.ll`, `.o` ou executável. Um módulo
inválido é erro interno de codegen, sai como `exit 65` com mensagem determinística
(`internal error: generated invalid LLVM IR: ...`) e nunca gera binário. O verificador é
rede de segurança para o GC e para qualquer mudança de lowering; não é uma opção do
usuário.

### 6. GC preciso e shadow stack ficam para depois

Shadow stack preciso, GC híbrido e `gc.statepoint` não entram agora. A decisão de root
preciso exigiria instrumentar temporários SSA, metadados de todos os objetos, alocador com
`free` e unwinding de exceções — um projeto de semanas, com risco de use-after-free
silencioso. O Boehm entrega o benefício de crescimento com risco muito menor. Se a
retenção conservadora ou o OOM não determinístico doerem de verdade, o caminho é um ADR novo
(híbrido antes de shadow stack).

## Consequências

### Positivas

- O binário deixa de morrer ao alocar em laço; programas com live set limitado rodam
  indefinidamente.
- Ciclos (listas, mapas, instâncias, closures) são coletados sem RC.
- A stdlib em Lox passa a ser viável; o kernel pode alocar strings/listas sem arena
  infinita.
- ABI e lowering atuais são preservados; o risco de regressão de codegen é baixo.
- O caminho de async do [ADR-0037](0037-async-direcao.md) continua compatível: frames
  suspensos no heap são visíveis ao Boehm.

### Negativas / custos

- `--emit=exe` ganha uma dependência de build (`libgc`/`bdw-gc`) e o CI precisa instalá-la;
  a mensagem de erro quando ela falta precisa ser clara.
- Coleta conservadora retém lixo por falsos positivos; o consumo de memória e o ponto de
  OOM não são determinísticos.
- O hard cap de 128 MiB não é o mesmo que “128 MiB úteis”: headers e free lists do Boehm
  consomem parte do orçamento; a margem de I1 em 64 MiB é deliberada.
- Strings inline podem exigir ponteiros interiores; se isso não for aceitável, o layout
  header+dados é dividido, com custo de mais uma alocação por string.
- Roots estáticos (globais, classes, literais) são um ponto sutil; um root esquecido vira
  use-after-free.
- `mod.verify()` e o OOM acrescentam superfície de teste e documentação.

### Neutras

- O tree-walk não muda; o I1 continua comparando stdout, stderr e exit code byte a byte.
- O timing de coleta não é observável na saída; endereço/PID/timestamp continuam proibidos
  pelo I3.
- `--emit=ll`/`--emit=obj` continuam sem `libgc`; só o executável linka.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| GC conservativo próprio, sem dependência | Reimplementa Boehm (stack bottom, registradores, plataformas, ASLR) e mantém o mesmo OOM não determinístico; manutenção sem ganho. |
| Híbrido: roots conservadores + heap preciso | Reduz retenção falsa, mas exige metadados de todos os objetos e alocador com `free`; 3–5 semanas e risco médio/alto. Fica como follow-up se doer. |
| Shadow stack preciso manual | Roots precisos e OOM determinístico, mas exige instrumentar temporários SSA, metadados de heap, free lists e integração com `setjmp`/`longjmp`; 4–8 semanas e risco alto de UAF silencioso. |
| `gc.statepoint` + stack maps do LLVM | Preciso, mas o llvmlite/LLVM 22 não oferece o caminho turnkey; pipeline de passes e runtime de stack maps é um projeto à parte. |
| Referência compartilhada + cycle collector | Write barriers em instâncias/listas/mapas/células, ciclos ainda exigem tracing e custo no caminho quente; já rejeitado no ADR-0031/0060. |
| Arena + escape/regiões | Não cobre closures/`Any`/classes e não resolve o caso geral; paliativo. |
| Só aumentar a arena / não fazer nada | Não resolve crescimento; a stdlib em Lox continua inviável. |
| Manter o OOM determinístico a qualquer custo | Exigiria GC preciso; o custo/risco não se justifica antes de medir a dor real do Boehm. |

## Como verificar

**Implementado em 2026-11-14:** `lox_alloc`/`lox_alloc_atomic` usam `GC_MALLOC`/
`GC_MALLOC_ATOMIC`; `lox_init` chama `GC_INIT`, fixa o hard cap de 128 MiB, instala o
`GC_set_oom_fn` e silencia os warnings do Boehm (`GC_ignore_warn_proc`) para o stderr
continuar determinístico. O link de `--emit=exe` ganhou `-lgc` e uma dica de instalação
quando a lib falta; o CI instala `libgc-dev`. Os testes de GC estão em
[`tests/test_backend.py`](../../tests/test_backend.py) (reciclagem, roots, `try`/`except`
e hard cap).

- [`tests/test_backend.py`](../../tests/test_backend.py): programa que aloca lixo em laço
  **passa** com GC; programa claramente acima do hard cap **falha** com `exit 70` e
  `Out of memory.`, duas execuções com o mesmo stderr e sem stdout antes da falha.
- Testes de roots: variável de topo, classe global sem instâncias, literal de string com
  cache, interior pointer de `LoxStr`, closures/células, `List`/`Map`/tupla/enum,
  `Any`, `try`/`except`/`finally` e ciclo de objetos; todos comparados com o tree-walk.
- [`tests/test_ir_verify.py`](../../tests/test_ir_verify.py): IR inválido vira
  `LLVMVerificationError`; o driver converte em `BackendError` (exit 65), sem binário.
- `make bench`: medir `string_scan`, listas/mapas e closures; a atualização do baseline é
  intencional e documentada no commit.
- `make check`: suíte, ruff, mypy strict, docs e determinismo.
- **Critério para revisitar:** retenção conservadora ou OOM começando a afetar programas
  legítimos; cap de 128 MiB insuficiente; falta de `libgc` em plataforma alvo; async
  exigindo roots precisas; ou divergência Python×C observada. Nesses casos, ADR novo
  (híbrido/shadow stack) — não ajuste silencioso do cap.

## Referências

- [ADR-0060](0060-orcamento-de-memoria.md) — contrato anterior da arena, substituído.
- [ADR-0031](0031-backend-nativo.md) — backend, `lox_alloc` e decisão 7.
- [ADR-0046](0046-closures-celulas-l4.md) — células, envs e closures.
- [ADR-0071](0071-primitivas-de-runtime.md) — kernel, cache de `LoxStr` e complexidade.
- [ADR-0037](0037-async-direcao.md) — frames materializáveis e GC.
- Boehm–Demers–Weiser GC: <https://www.hboehm.info/gc/>.
- [`../spec/garantias.md`](../spec/garantias.md) — contrato para quem usa.
