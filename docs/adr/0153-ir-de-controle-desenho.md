# ADR-0153 — IR de controle: modelo, invariantes e ciclo de vida

- **Status:** accepted (implemented, [#245](https://github.com/loxia-lang/loxia/issues/245))
- **Data:** 2026-11-27
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0065](0065-hir-lite-controle.md) (gatilho da HIR-lite),
  [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) (THIR e motores),
  [ADR-0031](0031-backend-nativo.md) (`llvmlite` e caminho de build),
  [ADR-0061](0061-l6-enums-match.md) (`match`/enums), [ADR-0062](0062-l6-excecoes-unwinding.md)
  (ABI de exceções), [ADR-0048](0048-abi-classes-l5.md) (ABI de classes),
  [ADR-0075](0075-diagnosticos-estruturados.md) (diagnósticos) e
  [ADR-0089](0089-stack-trace-de-runtime.md) (site de runtime).
- **Implementação:** `loxia_core/backend/control_ir/` (F1),
  `loxia_core/backend/lower_exceptions.py`, `loxia_core/backend/lower_enums.py`,
  `loxia_core/backend/lower_class_codegen.py`, `loxia_core/backend/lower.py`,
  `loxia_core/backend/lower_base.py` e `tests/test_control_ir.py`. A página
  `docs/tech/control-ir.md` descreve o modelo implementado (ver §9).

## Contexto

### O gatilho do ADR-0065

O [ADR-0065](0065-hir-lite-controle.md) definiu um gatilho explícito: se
`lower_exceptions.py`/`lower_enums.py` passar de ~350 linhas, parar e propor uma HIR-lite
**só para controle** (blocos, phi, cleanup, pattern), não para tipos/valores. Hoje eles têm
**385** e **434** linhas. O gatilho disparou.

O custo não é o tamanho do arquivo; é o controle manual repetido:

- `append_block`/`cbranch`/`phi.add_incoming` espalhados por exceções, `match`, classes,
  ternário, opcionais, containers e chamadas;
- checagens de `is_terminated` em quase todo `_stmt`;
- pilha de cleanup com `_cleanup_stack`, `_run_cleanups`, `_emitting_finally`,
  `LoopContext.cleanup_depth` e `_loop_transfer`;
- um `finally` emitido em vários caminhos, com cuidado para não reentrar em si mesmo;
- `phi` cujo conjunto de predecessores precisa bater com as arestas reais.

Isso funciona, mas é difícil de revisar e cada erro é um **miscompile** silencioso: phi sem
incoming, branch depois de terminador, `finally` pulado ou rodado duas vezes. O
[ADR-0149](0149-motores-primarios-thir-e-congelamento.md) §3 já decidiu que a IR de controle
é **interna ao backend**, não é pública, não substitui o THIR e não toca o oráculo.

### Duas IRs, dois papéis

| | THIR | IR de controle |
| --- | --- | --- |
| Forma | árvore | grafo de blocos |
| Responde | “o que o programa significa?” | “por onde a execução passa?” |
| Sabe | tipos, bindings, desugar | arestas, phi, cleanup |
| Consumidor | interpretador e lowering | lowering |
| Serializada? | sim, contrato de revisão (F2) | **não** |
| Pública? | sim (referência) | **não** |
| Vive | F2+ | F1–F4 (implementação Python) |

O THIR **não substitui** a IR de controle porque é uma árvore por decisão explícita: o
interpretador (F3) precisa avaliar uma árvore, não um CFG. O
[ADR-0149](0149-motores-primarios-thir-e-congelamento.md) diz: “O THIR não vira CFG. Se um
construto precisar de fluxo, ele desce para a IR de controle do backend.” A IR de controle,
por sua vez, não pode ganhar tipos/desugar: viraria um segundo checker e colocaria o I4 em
risco.

### O que “transitória” significa

A implementação Python é **transitória**: em F4 o lowering é reimplementado em Loxia e esse
módulo congela/morre com o backend Python. A **responsabilidade** não é transitória: um
compilador self-hosted que emita LLVM continua precisando de blocos, branches, phi e da
disciplina de cleanup de `try/finally`/`break`/`continue`/`return`.

No mundo final (ADR-0149), o pipeline é:

```
source .lx
   │ front (Loxia)
   ▼
AST ───────────────► AST JSON v2 (tooling/LSP/formatter; ponte no Nível 1)
   │ checker (Loxia)
   ▼
THIR ──────────────► THIR serializado (contrato/snapshot; ponte no Nível 1)
   ├─ THIR eval (Loxia)  → efeitos (REPL, --interpret, oráculo)
   └─ lowering (Loxia)   → control IR → LLVM builder → .o → cc → binário
```

Duas consequências:

1. O **front não emite THIR**; quem emite THIR é o checker. AST JSON é serialização de
   sintaxe, não IR semântica; no Nível 1 ele existe para a ponte com o checker Python
   (F5) e para tooling, não como entrada de motor.
2. O **interpretador não caminha pelo AST JSON**; ele caminha pela THIR. O tree-walk atual
   caminha pelo AST porque é o oráculo e carrega o checker junto; no F3 ele congela.

A IR de controle é, portanto, **transitória como código e conceitual como responsabilidade**.
É esse recorte que este ADR registra, para que a F1 não vire uma API eterna nem a F4
redescubra a matriz de cleanup.

## Decisão

### 1. Escopo

A IR de controle da F1 é:

- **interna ao backend**: não é API pública, não é serializada, não é versionada;
- **só controle**: blocos, terminadores, phi e pilha de cleanup;
- **sem tipos da linguagem**: recebe valores e tipos já loweringados (opacos);
- **sem instruções**: expressões continuam emitindo direto no alvo; não há IR de
  instruções nem otimizador;
- **sem mudança de ABI**: exceções, classes, `match` e runtime continuam com os contratos
  dos ADR-0061/0062/0048;
- **sem mudança de comportamento**: stdout/stderr/exit do corpus continuam byte a byte
  (I1/I3); o texto do `--emit=ll` pode mudar de rótulos/ordem, mas precisa ser determinístico.

Não entram na F1: THIR, `Switch`/decisão estruturada, `--dump-ir` como CLI, serialização,
otimizações, nova sintaxe, exceções recuperáveis e mudanças de ABI.

### 2. Modelo

O modelo é pequeno de propósito: **seis nós de controle e um contêiner**, com um punhado de
invariantes.

| Nó | Papel | Terminador? |
| --- | --- | --- |
| `ControlFunction` | dono dos blocos, da entrada e do estado de construção | — |
| `Block` | bloco básico; contém phi, terminador e um handle opaco para o alvo | não |
| `Phi` | merge de valores por predecessor | não (instrução) |
| `Br` | salto incondicional | sim |
| `CondBr` | salto condicional (dois sucessores) | sim |
| `Ret` | retorno (com valor opcional) | sim |
| `Unreachable` | caminho que não continua (`raise`, panic) | sim |

`Value` é um **handle opaco**: `llvmlite` hoje, LLVM-C/texto no futuro. A IR de controle não
define tipos de valor, instruções, constantes ou layout; ela só os referencia.

`match` não ganha nó especial na F1: vira cadeia de `CondBr` + `Phi` no bloco de merge. Se a
medição mostrar que uma decisão estruturada é necessária, isso é uma extensão com gatilho
próprio — não entra “de carona”.

### 3. Fronteira builder/emitter

A implementação é **one-pass**: o modelo e o alvo são construídos juntos, sem uma segunda
árvore de instruções. A fronteira é explícita:

- `ControlIR` é o dono do grafo e da profundidade de cleanup; `ControlIRBuilder` é o proxy
  que o lowering usa para **controle**: criar bloco, ramificar, retornar, criar phi,
  adicionar incoming e desenrolar cleanup.
- O proxy embrulha o builder do alvo (`llvmlite`, através de `llvm_ir`), materializa
  phi/terminadores e encaminha as demais instruções para o alvo.
- `verify_function(ControlFunction)`/`ControlIR.verify_all` roda no **modelo**, não no alvo. `dump(ControlFunction)` produz
  uma representação determinística (S-expression) para testes.
- Construtos migrados não chamam `llvm_ir.append_block`/`builder.phi` diretamente; usam o
  `ControlIRBuilder`. Construtos ainda não migrados mantêm o código atual até a sua fatia.
  Não se mistura os dois estilos dentro do mesmo construto.

Essa separação é o que permite a F4 reimplementar o modelo em Loxia sem arrastar
`llvmlite`: o emissor é descartável; o modelo e os invariantes são o contrato de desenho.

### 4. Pilha de cleanup

O coração da IR é a pilha de cleanup, não os blocos.

`CleanupContext` (em `lower_base.py`) continua guardando o estado lexical:

- `frame`: handle opaco do frame de `try` (ou `None` quando já foi desempilhado, no corpo de
  `except`/`finally`);
- `finally_body`: corpo léxico do `finally` (ou `None`);
- `scopes_depth`: profundidade de escopos a restaurar ao emitir o `finally` (o corpo do `try`
  já saiu de escopo; sem truncar, o `depth` do resolver aponta para o slot errado);
- `unwound`: marca que a região já foi consumida por `_run_cleanups`, para não decrementar a
  profundidade duas vezes no `_pop_cleanup` lexical.

O modelo acompanha apenas `ControlFunction.cleanup_depth`, incrementado por
`ControlIR.push_cleanup` e decrementado por `pop_cleanup`/`_run_cleanups`. A pilha real
(frame/finally/escopos) continua no lowering.

Operações:

- `_push_cleanup(...)` na entrada do `try` incrementa a profundidade;
- `_pop_cleanup(...)` na saída lexical normal decrementa (se a região ainda não foi
  consumida por um unwind);
- `_run_cleanups(limit)` para `return`/`break`/`continue`/`raise`: percorre as regiões da
  topo até `limit`, de cima para baixo; para cada uma, marca `unwound`, decrementa a
  profundidade, desempilha o frame (se houver) e emite o `finally` (uma vez); se o `finally`
  terminar, o terminador dele vence a ação pendente, mas o unwind **continua** nas regiões de
  fora (sem reemitir a atual); se completar normalmente, segue para a próxima; ao final, se
  nenhum terminador venceu, executa `action` (`ret`, `br`, rethrow etc.).

`break`/`continue` usam a profundidade da pilha na entrada do laço (`LoopContext.cleanup_depth`):
só desenrolam as regiões abertas **dentro** do laço.

Matriz de comportamento:

| Saída | Cleanups que rodam | Depois |
| --- | --- | --- |
| fim normal do `try` | o `try` atual | `br end` |
| `return` | todos até a função | `ret` |
| `break` | só os abertos dentro do laço | `br loop.end` |
| `continue` | só os abertos dentro do laço | `br loop.cond` |
| `raise` | até o handler/função | rethrow/throw |
| `return` dentro de `finally` | só os de fora (nunca o próprio) | `ret` |
| `raise` dentro de `finally` | só os de fora | novo raise |
| `finally` normal com ação pendente | o próprio já está emitindo (não reexecuta) | retoma a ação pendente |

Regras:

1. **LIFO**: as regiões desenrolam da mais interna para a mais externa.
2. **Uma vez por caminho**: um `finally` não pode ser emitido duas vezes no mesmo caminho;
   `emitting` impede a reentrância.
3. **Terminador vence**: se o `finally` termina (`return`/`raise`/`break`/`continue`), a ação
   pendente é descartada; os cleanups **de fora** ainda rodam.
4. **Ação pendente retoma**: se o `finally` completa normalmente, a ação original
   (`return`/`break`/`continue`/rethrow) continua depois dele.
5. **Valor antes do unwind**: um valor que atravessa cleanup (por exemplo, o valor de
   `return expr`) é materializado antes de desenrolar; não se lê um valor definido dentro da
   região depois que ela saiu.
6. **Escopo léxico**: o `finally` é emitido com os escopos truncados em `scope_depth`; o
   binding de `except` não vaza para o `finally`.
7. **Caminho de exceção**: o frame é desempilhado antes dos handlers; a região do handler tem
   `frame=None` e o mesmo `finally_body`.
8. **Fim de função**: a pilha chega vazia; `verify` rejeita o contrário.

#### Exemplo: `try/finally` com `return`

```lox
fn f() -> Int {
  try {
    return 1
  } finally {
    print("cleanup")
  }
}
```

O caminho normal vira, em conceito:

```
entry:
  frame = lox_try_push()
  status = setjmp(...)
  condbr status == 0, normal, caught

normal:
  ; corpo: return 1
  value = 1                 ; materializa antes do unwind (C6)
  unwind(depth=função, action=ret(value))
    → pop frame
    → emite finally
    → ret value

caught:
  ; handlers/rethrow; o frame já foi desempilhado
  ...
```

O `finally` é emitido **uma vez por caminho**; o `return` não emite `ret` antes de rodar o
cleanup. Se o `finally` tivesse o próprio `return`, ele venceria a ação pendente e só os
cleanups de fora rodariam.

### 5. Invariantes

`verify` policia o modelo. Falha de verificação é **bug interno do compilador** (ICE), nunca
um erro de linguagem (`not supported by the backend yet` é outra coisa, do I4).

| ID | Regra | O que quebra se falhar |
| --- | --- | --- |
| **C1** | Todo bloco tem exatamente um terminador, na última posição; nada é emitido depois dele. | LLVM inválido, fallthrough implícito. |
| **C2** | Todo sucessor pertence à mesma função; toda aresta é explícita; a entrada não tem predecessores. | Branch para bloco inexistente/estrangeiro; aresta fantasma. |
| **C3** | Todo phi tem exatamente um incoming por predecessor, sem duplicata, na ordem das arestas. | Phi sem valor ou com valor trocado; miscompile. |
| **C4** | Todo valor usado por terminador/phi é definido em bloco que domina o uso, ou é argumento/constante. Para phi, a definição domina o **predecessor** correspondente. | Uso antes da definição; valor errado. |
| **C5** | A pilha de cleanup é balanceada em todos os caminhos; no fim da função está vazia; não se sai de uma região sem rodá-la. | `finally` pulado ou rodado duas vezes. |
| **C6** | Valor que atravessa cleanup é materializado antes da saída da região. | Leitura de valor morto/errado depois do unwind. |
| **C7** | Rótulos, ordem de blocos, ordem de phi e ordem de incoming são determinísticos; nada de iterar `set`/`dict`/`id()`. | `.ll`/binário não determinístico (I3). |
| **C8** | Todo caminho de unwind/raise preserva o token/span do site original; nunca linha 0 sintética. | Stack trace/`e.site` no lugar errado; quebra do contrato de diagnóstico. |

`verify_function` impõe C1–C7. C4/C6 usam a origem/depth registrada pelo builder e são uma
**aproximação**: um valor definido e usado dentro do mesmo bloco que atravessa a saída de uma
região não é distinguido (ver `docs/tech/control-ir.md`). C8 é policiado pelos diagnósticos e
pelo diferencial, porque o modelo não carrega spans.

### 6. Determinismo

- Rótulos vêm de um contador monotônico com prefixo semântico (`try.normal`, `match.arm`),
  não de `id()` nem de hash.
- Blocos são ordenados pela criação; phi e incoming pela ordem das arestas.
- Compilar o mesmo programa duas vezes produz o mesmo `.ll` (teste), e o programa produz os
  mesmos bytes de stdout/stderr/exit (I1/I3).
- O `.ll` **não** precisa ser byte-idêntico ao de hoje: a migração pode renomear blocos e
  reordenar phi. O que não pode mudar é o comportamento do programa.

### 7. Migração

Fatias, cada uma verde antes da próxima:

1. **Modelo + builder + emitter + verifier + dump + testes** (sem migrar produção).
2. **Exceções**: `_raise`, `_try`, `_emit_finally`, `_run_cleanups` e `_loop_transfer`
   passam a usar o `ControlIR.new_block` e o proxy de controle. É a maior dor e a maior chance de simplificação.
3. **`match`**: `_match`/`_match_literal` usam o IR; o phi de resultado passa a ser do modelo.
4. **Classes**: as partes de controle de `lower_class_codegen.py` (construtor, `super`,
   inicialização de campos) migram; se não reduzirem complexidade, justificar e deixar fora,
   como o acceptance da #245 permite.
5. **Fechamento**: página `docs/tech/control-ir.md` a partir do código implementado, links em
   `docs/tech/arquitetura.md` e `loxia_core/AGENTS.md`, teste de completude da tabela de nós e,
   opcionalmente, um ratchet contra criação direta de blocos/phi fora de `control_ir/`.

Critério de “complexidade cai”: contar `append_block`, `phi` e checagens de `is_terminated`
nos três arquivos, mais a profundidade de aninhamento de `_try`/`_match`. LOC é secundário;
o plano já diz para não usar LOC como progresso.

Ratchet opcional (não bloqueia a F1): um teste que conta `append_block`/`phi` fora de
`control_ir/` e exige que o número não aumente. Assim a migração não regride sem precisar
migrar todos os lowerers de uma vez. Os lowerers restantes (ternário, opcionais, containers,
chamadas, ranges, bytes, strings) ficam na follow-up
[#263](https://github.com/loxia-lang/loxia/issues/263), que transforma o ratchet em boundary
global.

### 8. Verificação

Testes e critérios:

- **Unitários do modelo**: um teste por invariante C1–C7, com um caso que passa e um que
  falha; C8 é policiado pelos testes de diagnóstico/diferencial. Cobrem builder, troca de
  bloco, phi/incoming, unwind e reentrância de `finally`.
- **Dump determinístico**: S-expression de um CFG com phi; os construtos (`try/finally`,
  `match`, `break`) são cobertos pelo diferencial, não por um golden de IR.
- **Diferencial**: corpus atual verde; casos novos para as linhas da matriz de cleanup que
  não estiverem cobertas (`return` dentro de `finally`, `raise` dentro de `finally`, `finally`
  aninhado, `break`/`continue` dentro de `try`, match dentro de um bloco que retorna/levanta,
  binding de `except` fora do escopo do `finally`).
- **Determinismo**: compilar duas vezes o mesmo caso e comparar o `.ll`; rodar o binário e
  comparar stdout/stderr/exit.
- **`--emit=ll`**: inspeção de um caso por construto; não é contrato byte a byte.
- **Gate**: `make test-backend`, `make test` e `make check` verdes; I4 preservado.

### 9. Ciclo de vida e documentação

- **F1 (2026-11-27)**: este ADR é o registro durável do desenho; `docs/tech/control-ir.md`
  descreve o modelo implementado, com `sources:` apontando para `control_ir/**` e os lowerers
  migrados. A tabela de nós é policiada por um teste; `docs/tech/arquitetura.md` e
  `loxia_core/AGENTS.md` têm o link.
- **F2 (THIR)**: o THIR muda a **entrada** do lowering, não a existência da IR de controle;
  a página ganha a seção “THIR × control IR”. O THIR, sim, ganha spec/serialização/snapshot.
- **F3 (THIR eval)**: o interpretador/oráculo congela; a IR de controle não muda, porque
  pertence ao caminho do compilador.
- **F4 (compilador Loxia)**: o backend Python congela; a IR de controle é reimplementada em
  Loxia (provavelmente com o LLVM builder fornecendo blocos/phi e um módulo de cleanup para a
  parte específica de Loxia). A página vira insumo de port; depois recebe banner de congelada
  ou vai para arquivo, conforme G5 do ADR-0149.
- **Nunca**: spec pública, serialização, versionamento ou `--dump-ir` como contrato.

### 10. O que este ADR não decide

- **Emissão da F4**: LLVM-C em processo (um binding fino, análogo ao `llvmlite`) ou `.ll`
  textual + `clang`. O [ADR-0031](0031-backend-nativo.md) diz que `.ll` não é caminho de
  build, e o plano F4 diz `THIR → .ll → cc`; a tensão precisa ser resolvida em ADR próprio
  antes da F4. A IR de controle não depende da escolha: ela produz o grafo; o emissor é que
  muda.
- **Serialização do THIR no mundo final**: contrato/snapshot permanente ou necessidade do
  Nível 1 (ponte Python/Loxia) que pode sumir no Nível 2. Isso é decisão da F2/F3.
- **AST JSON**: ponte/tooling, não entrada de motor. A decisão de mantê-lo como contrato de
  front é da F5.

## Consequências

### Positivas

- O controle de exceções/`match`/classes sai do ad-hoc e ganha um lugar único.
- O verificador pega miscompiles que hoje só aparecem no diferencial ou em produção.
- A matriz de cleanup fica explícita e testável, em vez de espalhada em `_run_cleanups` e
  `_emitting_finally`.
- A F2 (THIR) mexe na entrada do lowering com o controle já centralizado.
- A F4 herda um modelo e um conjunto de invariantes para reimplementar, em vez de redescobrir.
- O `.ll` fica determinístico e os rótulos ficam legíveis.

### Negativas / custos

- Mais uma indireção no lowering; a implementação Python será descartada na F4.
- A fronteira builder/emitter precisa ser mantida; se vazar, volta o controle manual.
- Durante a migração convivem dois estilos; sem ratchet, a regressão é silenciosa.
- Não é contrato público: não dá para prometer estabilidade de API nem serialização.
- A reimplementação em Loxia ainda é trabalho de F4; o ADR não a elimina.

### Neutras

- Nenhuma mudança de ABI, sintaxe ou comportamento observável.
- O texto do `--emit=ll` pode mudar; o comportamento do programa não.
- O THIR continua sendo o eixo semântico; a IR de controle continua sendo encanamento.
- O módulo separado é uma escolha de design; a responsabilidade de cleanup é que é essencial.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| HIR completa (CFG/SSA) antes de exceções | O LLVM já otimiza; a dor é semântica/controle, não otimização; custo alto para um alvo. |
| Wrapper fino do `llvmlite`, sem modelo | Resolve pouco: não há onde verificar invariantes nem o que a F4 possa reaproveitar como desenho. |
| IR de instruções completa + emit | Duplica o LLVM, vira mini-compilador e aumenta a superfície que será descartada. |
| Emitir `.ll` textual já na F1 | É decisão de F4; o ADR-0031 rejeita `.ll` como caminho de build. A F1 usa o alvo atual. |
| Não fazer nada e conviver com o manual | O gatilho do ADR-0065 já disparou; a complexidade cresce a cada construto novo. |
| Fazer THIR primeiro | THIR é árvore; não resolve o controle. A F2 continua necessária e a dor atual ficaria. |
| Spec pública/serializada da IR de controle | Contrato que não queremos manter; a IR é interna e transitória. O THIR é que merece spec. |
| Um `Switch`/decisão estruturada para `match` | `CondBr` + `Phi` cobre a F1; nó novo sem necessidade é dívida. |

## Como verificar

- [x] `loxia_core/backend/control_ir/` com modelo, builder, emitter, verifier e dump.
- [x] Testes C1–C7 (um caso válido e um inválido por invariante); C8 pelos
      diagnósticos/diferencial.
- [x] Testes da matriz de cleanup, incluindo `continue` dentro de `try/finally`.
- [x] `lower_exceptions`, `lower_enums` e as partes de controle de `lower_class_codegen`
      usando o `ControlIRBuilder`; sem `append_block`/`block_of` diretos nesses arquivos.
- [x] Corpus diferencial verde; stdout/stderr/exit iguais ao `--interpret` (I1).
- [x] `--emit=ll` inspecionado; `tests/test_backend.py` compara duas compilações (I3).
- [x] I4 preservado: nenhum programa com `--check` limpo falha por tipo no lowering.
- [x] `make test-backend`, `make test` e `make check` verdes.
- [x] Contagem de `append_block`/`phi`/`is_terminated` registrada nas fatias (16→0 em
      `lower_class_codegen.py`); LOC só como contexto.
- [x] `docs/tech/control-ir.md` criada a partir do código, com `sources:`, tabela de nós
      policiada e links em `arquitetura.md`/`AGENTS.md`.

**Critério para revisitar:** a IR passar de ~15 nós ou ganhar consumidor externo; a F4
escolher emissão textual e exigir mudança no emissor; o THIR começar a carregar controle
(sinal de escopo errado); a migração não reduzir complexidade de forma justificável; ou o
verificador virar fonte frequente de falso positivo.

## Referências

- [ADR-0065](0065-hir-lite-controle.md) — gatilho da HIR-lite de controle.
- [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) — THIR, IR de controle e
  congelamento.
- [ADR-0031](0031-backend-nativo.md) — `llvmlite`, objeto e `.ll` como inspeção.
- [ADR-0062](0062-l6-excecoes-unwinding.md) — ABI de exceções e cleanup.
- [ADR-0061](0061-l6-enums-match.md) — enums e `match`.
- [ADR-0048](0048-abi-classes-l5.md) — ABI de classes.
- [`docs/plano-de-motores.md`](../plano-de-motores.md) — fases, portões e F1.
- [`docs/tech/arquitetura.md`](../tech/arquitetura.md) — mapa de módulos.
