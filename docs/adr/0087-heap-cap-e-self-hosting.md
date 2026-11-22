> **Atualização (2026-11-21):** a limitação de campo do próprio tipo de classe foi
> resolvida — `class Node { var next: Node? }` compila e roda no backend, com caso no
> corpus. Campo `Any` direto continua `E4001`; para o AST self-hosted use enum com payload
> `Any` ou `List[Any]`. O texto abaixo é o registro histórico da decisão original.

# ADR-0087 — Hard cap de heap de 512 MiB e `--max-heap` de build

- **Status:** accepted (implementado)
- **Data:** 2026-11-15
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  [ADR-0031](0031-backend-nativo.md) (backend),
  [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) (GC Boehm e contrato de memória),
  [ADR-0077](0077-limite-de-pilha.md) (pilha), [`../../TODO.md`](../../TODO.md)
  §3/§10/§13.7,
  [`../spec/garantias.md`](../spec/garantias.md)
- **Implementação:** [`runtime/core.c`](../../runtime/core.c) (`LOX_GC_MAX_HEAP_BYTES`),
  [`loxia_core/execution/limits.py`](../../loxia_core/execution/limits.py),
  [`loxia_core/backend/driver.py`](../../loxia_core/backend/driver.py),
  [`loxia/cli.py`](../../loxia/cli.py), [`tests/test_backend.py`](../../tests/test_backend.py)

## Contexto

O [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) fixou hard cap de **128 MiB** de
heap coletado e I1 até 64 MiB de memória viva. Esse número foi escolhido para o MVP e
para manter o teste de OOM barato, não para cargas grandes.

Com a aproximação do self-hosting/front-end em Lox, a pergunta mudou: um compilador
self-hosted mantém tokens, AST, tabela de símbolos e saída ao mesmo tempo; o cap de
128 MiB pode ser o teto antes do fim do parse. Medições deste ambiente (Boehm, binário
`--emit=exe`, nós de interface com 3 campos + string):

| Carga viva | Com 128 MiB |
| --- | --- |
| 500k nós | ok (~63 MB RSS) |
| 1M nós | ok (~134 MB RSS, no limite) |
| 2M nós | `Out of memory.`, exit 70 |
| 500k nós com `List[Any]` por nó | ok (~135 MB RSS) |
| 1M nós com lista por nó | `Out of memory.`, exit 70 |

Ou seja: 128 MiB compra ~1M nós pequenos ou ~500k nós com uma lista por nó. Para o
front-end Python atual (~836 KB/24k linhas) uma versão Lox provavelmente é maior; com
tokens + AST + símbolos + saída, 128 MiB é apertado e 512 MiB dá 4x de folga. O cap maior
não é “toda a RAM”: continua sendo um orçamento determinístico, agora menos restritivo.

### Achado colateral para self-hosting

O backend ainda **não aceita campo do próprio tipo de classe**:

```lox
class Node {
  var next: Node?   # E4001: Class 'Node' is not supported by the backend yet.
}
```

O mesmo grafo funciona via interface, e foi validado no backend:

```lox
interface Expr {}
class Lit implements Expr { val value: Int; fn init(value: Int) { this.value = value } }
class Bin implements Expr {
  val left: Expr?
  val right: Expr?
  fn init(left: Expr?, right: Expr?) { this.left = left; this.right = right }
}
```

Campo `Any` também não é aceito; `List[Any]` funciona. O AST self-hosted deve usar
interfaces para filhos recursivos até o backend suportar classe recursiva. Isso é
independente do cap de heap e fica registrado como pré-requisito de self-hosting, não
como decisão deste ADR.

## Decisão

### 1. Default de 512 MiB

O hard cap default do binário sobe de **128 MiB para 512 MiB**
(`DEFAULT_HEAP_BYTES` em `loxia_core/execution/limits.py`; fallback em `runtime/core.c`). O runtime
recebe o valor por `-DLOX_GC_MAX_HEAP_BYTES=...ull` na compilação do `runtime.o`; o
driver sempre passa o valor, então fonte C e Python não divergem.

### 2. `--max-heap` no build, não no runtime

`uv run main.py --emit=exe --max-heap=2G -o app prog.lx` compila o runtime com o teto
escolhido. Regras:

- só com `--emit=exe` (é o único modo que linka o runtime); erro de uso nos outros;
- default `512M`; mínimo `32M`; máximo `8G`;
- aceita bytes puros e sufixos `K`/`M`/`G` (binários, 1024);
- o valor é **baked** no binário; não há env var nem flag de runtime, então um binário
  tem sempre o mesmo teto;
- a chave do cache de `runtime.o` inclui cap, `MAX_CALL_DEPTH` e a reserva de pilha;
- `--emit=ll`/`obj` não mudam (não linkam runtime).

O flag existe para dois casos concretos: self-hosting/compilador com `--max-heap=2G` e
sandbox/MCP com um teto menor (ex.: `64M`), sem mudar o default econômico.

### 3. Contrato e I1 não mudam

- **I1 continua cobrindo até 64 MiB de memória viva.** Programas acima disso já estavam
  fora do corpus; o cap maior só permite que rodem. Self-hosting fica declarado fora do
  I1 até existir um corpus self-hosted; se isso for exigido, é outro aumento de orçamento
  e outro corpus.
- O **ponto exato** do OOM continua não determinístico (Boehm conservador); o que é
  estável é canal, mensagem (`Out of memory.`) e exit 70.
- O interpretador continua sem teto (GC do Python); a assimetria é declarada.
- A pilha é orçamento separado ([ADR-0077](0077-limite-de-pilha.md)); 512 MiB de heap
  não incluem a pilha nem o runtime.

### 4. Testes

- O teste de OOM constrói com `--max-heap=128M` para continuar barato e determinístico.
- Um teste novo aloca ~200 MiB de strings vivas e prova que o default de 512 MiB
  sobrevive; com o override de 128 MiB, o mesmo programa morre.
- `--max-heap` sem `--emit=exe`, unidade inválida e limites são cobertos no CLI.
- `make docs-sync` mantém o bloco de status do corpus; `docs/spec/garantias.md` e
  `docs/tech/arquitetura.md` refletem o número novo.

### 5. Fora de escopo

- Remover o cap e deixar o SO matar o processo (SIGKILL, sem diagnóstico).
- Cap configurável por ambiente ou em runtime: quebra a ideia de binário determinístico.
- GC preciso, shadow stack ou alocador com `free`: o Boehm continua; reduzir retenção
  conservadora é projeto separado.
- `fs.open`/streaming para CSV de 4 GB: é feature de stdlib/kernel, registrada no
  `TODO.md` §10; o cap maior não substitui streaming.

## Consequências

### Positivas

- O compilador self-hosted/front-end em Lox tem 4x mais folga sem mudar o default de
  quem só roda programas pequenos.
- O teto continua determinístico e embutido no binário; MCP/sandbox pode baixar no build.
- O teste de OOM permanece barato via override, e o caminho real de 512 MiB é testado.
- Nenhuma mudança de ABI, lowering ou GC: só o valor do cap e o plumbing do build.

### Negativas / custos

- Um programa com bug de alocação pode consumir até 512 MiB antes de falhar; o default
  anterior falhava em 128 MiB. O OOM continua controlado, mas o RSS máximo cresce.
- O teste de 200 MiB adiciona memória/tempo à suíte nativa.
- O cap de 512 MiB não é “512 MiB úteis”: headers/free lists do Boehm consomem parte.
- Ainda não cobre cargas de vários GB; para isso, build com `--max-heap=...` e RAM
  suficiente, ou streaming.
- O backend não aceita classe recursiva nem campo `Any`; self-hosting exige o padrão de
  interfaces (documentado acima), não resolvido por este ADR.

### Neutras

- I1 permanece em 64 MiB live; o número do cap não muda a promessa.
- A pilha continua em 10.000 chamadas / 64 MiB (ADR-0077).
- `--emit=ll`/`obj` não são afetados.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter 128 MiB | Apertado para self-hosting; ~500k nós com lista já estouram. |
| Default de 1 GiB ou mais | Aumenta o RSS de um programa descontrolado e o custo do teste de OOM; 512 MiB é o ponto econômico. |
| Remover o cap | O SO mata com SIGKILL, sem `Out of memory.` nem exit 70; quebra o contrato de falha determinística. |
| `LOX_MAX_HEAP` por env | Binário muda de comportamento sem rebuild; viola I3 e a ideia de teto fixo. |
| `--max-heap` em runtime | O binário precisa separar o flag dos `args()` do programa; o build já resolve e mantém o contrato. |
| GC preciso/RC para reduzir retenção | Semanas/meses e risco de UAF; o Boehm entrega o necessário agora. |
| Streaming obrigatório para tudo | Não resolve árvores/AST que precisam estar vivos; streaming complementa, não substitui o cap. |

## Como verificar

- `uv run pytest -m backend -k "hard_cap or heap_default"`.
- `uv run main.py --emit=exe --max-heap=128M -o app prog.lx` vs default com o programa de
  ~200 MiB.
- `uv run main.py --max-heap=128M prog.lx` → exit 2, “requires --emit=exe”.
- `make check` verde; `docs/spec/garantias.md` e `docs/tech/arquitetura.md` com 512 MiB.

**Critério para revisitar:** self-hosting não couber em 512 MiB; OOM de 512 MiB doer em
CLI/CI; ou necessidade de cargas de vários GB por processo. Nesses casos, ADR novo com
medição — não ajuste silencioso do default.

## Referências

- [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) — GC Boehm, roots, OOM e I1.
- [ADR-0077](0077-limite-de-pilha.md) — orçamento de pilha.
- [`../spec/garantias.md`](../spec/garantias.md) — promessas atuais.
- [`../../TODO.md`](../../TODO.md) §10 — `fs.open`/streaming.
