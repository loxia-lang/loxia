# TODO — Roadmap e ideias

Documento vivo do projeto: o que **falta** na linguagem, no checker, no runtime e no
backend. O que já foi implementado **não fica aqui**: vira ADR, [`docs/spec/`](docs/spec/) e
[`docs/decisoes.md`](docs/decisoes.md). Discussões em aberto ficam em
[`IDEIAS.md`](IDEIAS.md); tipos e números em [`TIPOS.md`](TIPOS.md).

> **Escopo:** nada neste arquivo é 1.0. O escopo 1.0 está congelado no
> [ADR-0026](docs/adr/0026-freeze-1.0.md) (com T3b/D-8 como exceções); este TODO é
> **pós-1.0**. Para o mapa completo, veja [`ESCOPO.md`](ESCOPO.md).

**Legenda:** `P0` agora · `P1` próximo · `P2` depois · `P3` algum dia
**Esforço:** `S` (horas) · `M` (dias) · `L` (semanas) · `XL` (meses)

> Regra de ouro: fechar as definições que cada nível consome **antes** de codá-lo.
> Cada feature nova entra com teste; cada mudança de sintaxe entra documentada no
> mesmo commit.

---

## 0. Fila única

A fila ativa é curta: **dogfooding do `loxia fmt` em Lox**, **M8/M9** e a trilha de
publicação (§14). LSP-2 e o lote de fixes estão fechados; o que resta deles está na §7.
O status por nível é **gerado** em [`docs/spec/garantias.md`](docs/spec/garantias.md) a
partir de [`tests/corpus_manifest.py`](tests/corpus_manifest.py) — não copie números para cá.


### 0.2 Ordem de execução

1. [ ] **Dogfooding do formatter** (`P2`/`L`): portar `loxia fmt` para Lox com paridade
       byte a byte contra o Python ([ADR-0092](docs/adr/0092-estilo-e-formatter.md), §13.7).
2. [ ] **M8** (`P2`): performance restante; JIT no REPL é P3 e não bloqueia.
3. [ ] **M9** (`P2`): ecossistema — cliente VS Code/`workspace/symbol`, site e playground
       (ADRs 0090–0093; §7 e §14).
4. [ ] **Publicação** (`P2`, paralela): §14 (repo público, site, MCP, distribuição).

> **Trilha paralela:** a §14 (publicação, distribuição, pacotes, corpus de conformidade e
> docs de usuário) não bloqueia nenhum nível da linguagem/backend e pode andar junto com a
> fila acima. Ela é pré-requisito de **adoção**, não de correção.

## 3. Diagnósticos

O desenho e a primeira entrega estão no
[ADR-0075](docs/adr/0075-diagnosticos-estruturados.md): modelo `Diagnostic`,
códigos estáveis por família, spans (linha/coluna/offset), `human`/`short`/`json`,
ordenação/dedup/cap e caminho relativo determinístico. O catálogo em
[`docs/spec/erros.md`](docs/spec/erros.md) é **gerado** a partir de
`loxia_core/diagnostics/codes.py` (`make codes`).

### 3.1 O que ainda falta

- [ ] **`notes` de proveniência** (`P2`): "o valor vem de `pessoa.nome` (linha 7)".
      O `SourceIndex` de spans de expressão já existe; falta o checker consumi-lo para
      produzir as `notes` ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)).

**Anti-metas:** não imprimir direto do scanner/parser (só coletar); não usar `assert` do
Python para validar código do usuário; não classificar código por prefixo de mensagem.

### 6.9 CLI alvo

```bash
loxia run script.lx
loxia check script.lx
loxia build script.lx --emit=ll|obj|exe -o app
loxia ast script.lx
loxia fmt [--check] script.lx
loxia doc std/strings.lx --json
loxia explain E2001
loxia capabilities --json
loxia lsp
loxia repl                    # REPL, com :type, :ast
```

`--check`, `--emit` e `--dump-ast` continuam como aliases; `main.py` e a invocação atual
não quebram ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)).

### 6.10 Bônus: WebAssembly

`llvmlite` sabe emitir para **wasm32** (`Target.from_triple("wasm32-unknown-unknown")`).
Isso permitiria um playground no navegador sem Pyodide — a linguagem rodando a 100% no
browser. Guardar como ideia P3 (precisa de runtime mínimo em wasm e de uma ABI de
imports para `print`).

### 6.11 Corpus diferencial (bloqueia o I1)

Regra: o I1 vale para o **corpus anotado e classificado**, nunca para o que o backend
"quase" faz. Todo caso está em `LEVELS`, `PENDING` ou `NEGATIVE`
([`tests/corpus_manifest.py`](tests/corpus_manifest.py)); promover caso = mover de
`PENDING` para `LEVELS` no mesmo commit, com o teste diferencial verde nos três canais.
O status atual (quantos compilam, quantos em `PENDING`) é **gerado** em
[`docs/spec/garantias.md`](docs/spec/garantias.md) — não duplique aqui.

**Teto** ([ADR-0064](docs/adr/0064-orcamento-do-corpus.md)): `PENDING` ≤ 5% do corpus,
sempre com nível/motivo, e `l?` proibido. Hoje `PENDING` está zerado; o I1 cobre `LEVELS`,
e o teto impede que o teste verde vire ficção. Caso novo sem backend espera em issue/branch
em vez de inflar `PENDING`.

```bash
uv sync --extra llvm
uv run pytest tests/test_backend.py -q
```

---

## 7. Tooling e qualidade

- [ ] `P2` E3004 (anotação ausente) — critérios em
      [`docs/tech/fixes.md`](docs/tech/fixes.md).
- [ ] `P2` `loxia fmt`: `fn` em método, trailing comma/reflow e dogfood em Lox após a T3
      ([ADR-0092](docs/adr/0092-estilo-e-formatter.md)).
- [ ] `P2` LSP restante: `workspace/symbol` e cliente VS Code; `codeAction`, `rename`
      (local e cross-file conservador) e `SourceIndex` já implementados
      ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)).
- [ ] `P3` tree-sitter grammar (complemento do LSP; não substitui).
- [ ] `P3` fuzzing do scanner/parser com `hypothesis`.
- [ ] `P3` snapshot de AST em arquivo.
- [ ] `P3` site publicado a partir de `docs/` — ver §14.2 (stack, i18n e gate).
- [ ] `P3` servidor MCP (`loxia-mcp`) — ver §14.3; depende do CLI agent-friendly acima.

---

## 8. Lox2: o que ainda vale

| Recurso | Status | Nota |
| --- | --- | --- |
| FFI com C | ⏸ | **não haverá FFI genérica**: kernel fixo de primitivas ([ADR-0071](docs/adr/0071-primitivas-de-runtime.md)); reavaliar só com dor demonstrada |
| `async`/`await` | ⏳ | ADR-0037 em revisão: `poll`/`proc` antes de async; colored/`Task[T]` só com caso que `poll` não resolva |

Fora: VM própria, GC geracional, JIT tracing, cache de bytecode e `Object` raiz — o LLVM
cobre o codegen e o escopo humano manda.

---

## 9. Milestones pendentes

M0–M7 estão fechados (ver [`docs/decisoes.md`](docs/decisoes.md)). Falta:

| # | Marco | Critério de pronto | Estado |
| --- | --- | --- | --- |
| **M8** | Performance | `-O2` e benchmarks feitos; JIT no REPL é P3 e não bloqueia | 🟡 |
| **M9** | Ecossistema | formatter, LSP, docs e playground — escopo definido nos [ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md) a [ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md) | 🟡 |

**Regra:** a ordem oficial é a §0. Se algo mudar a semântica de um nível já compilado, o
nível afetado volta para a fila com caso diferencial.

**Async (ADR-0037) — em revisão (2026-11-16):** a direção colored/`Task[T]` continua,
mas a ordem mudou com a proposta de host capabilities
([`IDEIAS.md`](IDEIAS.md) I-11): `poll`/`proc` resolvem I/O concorrente sem thread e devem
vir antes de async. Async só entra com um caso que `poll` não resolva e deixa de ser
pré-requisito de M8; revisar o ADR-0037 antes de codar. Paralelismo/multithread segue
fora — não é async.

### 9.1 Divergências I1 conhecidas (fora do corpus)

No sentido estrito (bytes finais de stdout/stderr e exit code) **não há divergência
conhecida fora do corpus**. Limite declarado (regra da linguagem, não do lowering):
`is`/`as` com argumentos de tipo em classe/enum é recusado pelo checker (`E3000`) e o
tree-walk levanta `R1014`.

**Limitação de backend (E4001, não é divergência I1):** `fn listOf[T](...) -> Gen[List[T]]`
passa no `--check` e o binário recusa com `Unbound type parameter 'T'`; `std.property`
expõe `listOfInt` e `listOfString` até o lowering substituir o TyVar antes de instanciar a
classe.

---

## 10. Parque de diversões (ideias soltas)

- [ ] **Compilar o próprio interpretador?** (self-hosting) — o *front-end* já é
      self-hostable hoje (lexer em Lox compila nativo e bate a saída); o compilador inteiro
      depende de I/O, GC e do resto do L6. Escada em §13.7 (passo 1). P3/XL.
- [ ] **LSP em Loxia** (`P3`, `XL`, **não decidido**) — avaliado em 2026-11-16: o LSP local
      é stdio, não rede ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)); o que falta
      de kernel é pouco (`io.readUtf8`/`io.flush` já existem — §13.9) e o bloqueio
      real é não haver front-end/checker chamável de um programa Loxia. Caminho B (delegar
      a `loxia check --error-format=json` via `proc.spawn`) não duplica regra; caminho C
      (front-end em Loxia) cria duas verdades de diagnóstico (I4). Por ora o servidor fica
      em Python; revisitar depois do self-hosting. Ver [`IDEIAS.md`](IDEIAS.md) I-11.
- [ ] **`loxia fmt`** — o formatter shipped começa em Python (referência, idempotente); o
      exercício de dogfooding em Lox (parser + AST printer) entra depois da T3, com
      paridade byte a byte ([ADR-0092](docs/adr/0092-estilo-e-formatter.md), §13.7).
- [ ] **`fs.open` + leitura/escrita em streaming** (`P2`, `M`) — handle de arquivo
      explícito, no espírito do `open()` do Python, para não materializar arquivos grandes
      em `String`/`List[String]` (o `readLines` atual lê o arquivo inteiro). Ideias:
      - `fs.open(path, mode) -> File?` com modos `"r"`, `"w"`, `"a"`, `"r+"`, `"w+"`,
        `"a+"` (texto UTF-8; binário/`Bytes` fica fora até existir o tipo); `File` com
        `readLine() -> String?` (nil = EOF), `readAll() -> String`, `read(n) -> String?`,
        `write(text)`, `flush()`, `close()`, `seek`/`tell` (avaliar), `lines()` (avaliar);
      - **fechamento automático**: Loxia não tem `with`. Opções: (a) helper de stdlib
        `fs.withOpen(path, mode, fn(f: File) { ... })` que fecha em `finally`, sem sintaxe
        nova; (b) `with`/`defer` de verdade, só com aprovação do gate do
        [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md); (c) finalizer/GC não é
        determinístico no Boehm, então não;
      - erros: `File?` para abrir e `String?` para EOF, erro de I/O vira `LoxRuntimeError`;
        `close()` idempotente; usar depois de fechar é erro; exceção no callback de
        `withOpen` fecha o handle;
      - custo: dois motores (`FILE*` no runtime, file object no Python), testes com diretório
        temporário, UTF-8/CRLF, append, leitura linha a linha com memória limitada; I/O é
        ambiente (fora do I1), sem caminho absoluto na saída;
      - relação: `readText`/`readLines` continuam como conveniência; `fs.open` é o caminho
        para CSV/logs grandes e para o `loxia fmt`/self-hosting.
- [ ] **Playground WASM** (target `wasm32` do LLVM) rodando no navegador.
- [ ] **REPL com `:type`** — mostra o tipo inferido de uma expressão antes de rodar.
- [ ] **Debugger (DAP)** — breakpoints no tree-walk primeiro; no nativo depois.
- [ ] **Hot reload** no REPL (redefinir funções sem perder estado).
- [ ] **Benchmark suite pública** (fib, nbody, mandelbrot) para acompanhar regressões.
- [ ] **Compilar para um Arduino/Pico?** (LLVM target `thumbv6m`) — suicídio de escopo,
      mas divertido de tentar um dia.
- [ ] **Dialeto embutido**: `lox` como linguagem de script de um app Python (via CFFI).
- [ ] **Gerador de AST a partir de schema** (o livro faz à mão; um script evita erro
      quando a linguagem crescer).

### Generics pós-MVP — adiados (2026-11-13)

Nada aqui será feito por enquanto. Retomar só com dor demonstrada (um caso de uso real);
com constraints em funções ([ADR-0081](docs/adr/0081-constraints-generics.md)), métodos
genéricos passam a ser desenháveis, mas continuam fora. O desenho de classes está no
[ADR-0040](docs/adr/0040-generics-classes-desenho.md) §"Em aberto".

- [ ] `fn map[U]` — métodos genéricos: a função livre cobre; exigiria bounds no método e
      monomorfização por `this`.
- [ ] `class IntBox(Box[Int])` — herança de instanciação: composição cobre; exige
      substituição em cadeia no checker e aumenta a superfície que o backend tem que
      reproduzir (I1).
- [ ] `is`/`as Box[Int]` — reificação: exige tipos em runtime (*witnesses*), conflita com o
      erasure e com o tree-walk rodar sem `--check`; o erro explícito atual é o
      comportamento correto.

---

## 11. Decisões em aberto

Só o que ainda **não** foi decidido. Fechadas: [`docs/decisoes.md`](docs/decisoes.md);
pendências de tipo: [`TIPOS.md`](TIPOS.md).

1. **Generics além do MVP:** continuam em aberto type application explícita e função
   genérica como valor; métodos genéricos, herança de `Box[Int]` e `is/as` reificado estão
   adiados (§10). Interfaces nominais estão implementadas no tree-walk/checker e no
   backend ([ADR-0080](docs/adr/0080-interfaces-nominais-implementacao.md)); constraints
   de função estão implementadas ([ADR-0081](docs/adr/0081-constraints-generics.md)) e
   constraints em classes seguem pós-MVP.
2. **Stdlib pós-1.0:** T1/T2/T3 concluídas. Restam `std.utf8` (`byteLen`/coluna UTF-16),
   `fs.open` em streaming (§13.9) e as capacidades de host não aprovadas. `time`
   não determinístico e transcendentais de `math` continuam fora do I3.
3. **Interfaces genéricas e constraints em classes:** `interface I[T]` e
   `class C[T: I]` continuam em aberto; constraints de função já existem
   ([ADR-0081](docs/adr/0081-constraints-generics.md)).
4. **Contratos e agentes:** `requires`/`ensures`/`invariant` e `--contracts` default
   continuam em aberto ([`IDEIAS.md`](IDEIAS.md) I-4); o schema JSON v1 com `fixes[]` já
   está implementado ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)).
5. **`if`/bloco como expressão:** fora da 1.0; reavaliar quando houver dor real.
6. **Paralelismo (multithread):** em avaliação no [`IDEIAS.md`](IDEIAS.md); async é
   concorrência single-thread ([ADR-0037](docs/adr/0037-async-direcao.md)), não paralelismo.
7. **HIR-lite — gate explícito:** não construir agora. Trocar para HIR-lite só se um
   destes gatilhos disparar ([ADR-0065](docs/adr/0065-hir-lite-controle.md)):
   `lower_exceptions.py`/`lower_enums.py` passarem de ~350 linhas, o lowering precisar de
   mais de 2 níveis manuais de blocos/phi, ou uma feature exigir CFG explícito (cleanup
   dinâmico completo, JIT). `Any` e containers sozinhos não disparam. Stack trace com
   frames **não** disparou: array de frames resolvido sem CFG
   ([ADR-0089](docs/adr/0089-stack-trace-de-runtime.md)).
8. **Cleanup de exceções:** `finally` cobre o corpus; cleanup dinâmico completo em
   `raise` através de frames aninhados é dívida declarada, não bloqueia a stdlib.
9. **Imports:** [ADR-0073](docs/adr/0073-imports-modulos.md) implementado; única pendência
   é `..` fora da raiz (§13.5).

---

## 12. Referências

- Lox2: <https://github.com/HallofFamer/Lox2> · docs <https://mysidia-inc.gitbook.io/lox2>
  (ler `notes/DESIGN.md` e `notes/TYPESYSTEM.md`).
- `llvmlite`: <https://llvmlite.readthedocs.io/> · <https://github.com/numba/llvmlite>
- LLVM LangRef: <https://llvm.org/docs/LangRef.html> · tutorial Kaleidoscope:
  <https://llvm.org/docs/tutorial/>
- *Mapping High-Level Constructs to LLVM IR*:
  <https://mapping-high-level-constructs-to-llvm-ir.readthedocs.io/> (closures, vtables, GC)
- Hindley–Milner (para o modelo mental de unificação):
  <https://en.wikipedia.org/wiki/Hindley%E2%80%93Milner_type_system>

---

## 13. Stdlib, kernel de primitivas e módulos

> **Escopo:** pós-1.0; **não** bloqueia L6/L7 (§0). O kernel v1 está concluído
> ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)). Decisões:
> [ADR-0071](docs/adr/0071-primitivas-de-runtime.md) (primitivas e complexidade),
> [ADR-0072](docs/adr/0072-stdlib-batteries.md) (política de batteries) e
> [ADR-0073](docs/adr/0073-imports-modulos.md) (imports — **implementado**).
>
> **Regra de ouro:** kernel = SO ou representação; tudo o mais é Lox. Nenhuma lógica de
> negócio em primitiva, nenhuma primitiva que Lox faria em O(n).
>
> **Fora:** regex, cripto, rede, async, timezone DB, i18n, YAML/TOML, UUID, bigint.
> `subprocesso` entrou via [ADR-0095](docs/adr/0095-processos-streams-poll.md); `rede`
> segue em revisão na §13.9/[`IDEIAS.md`](IDEIAS.md) I-11 — nada decidido.

### 13.1 Camadas

| Camada | O que entra | Implementações | Onde |
| --- | --- | --- | --- |
| kernel | syscalls e representação | Python (oráculo) + C (binário) | `loxia_core/execution/primitives.py`, `runtime/kernel.c` (+ `kernel_gen.h` gerado) |
| std | biblioteca | **uma** (Lox) | `std/*.lx` |
| módulos | nomeação e carga | loader/desugar, sem lógica | `loxia_core/loader/` |

**Kernel concluído** com **29** primitivas: `args`, `io.*` (incluindo `readAll`,
`readUtf8` e `flush`), `fs.*` (`exists`, `listDir`), `os.*`, `time.*`, `substr`, `join`,
`charCodeAt`, `fromCodePoint` e `process.*` (spawn/streams/read/write/wait/kill/close/poll,
[ADR-0095](docs/adr/0095-processos-streams-poll.md)).
O teto subiu de 15 para 17 na T2 ([ADR-0079](docs/adr/0079-stdlib-t2.md)), para 19 com
stdio por bytes ([ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md)) e para 29 com
processos/`poll` ([ADR-0095](docs/adr/0095-processos-streams-poll.md)) — o teto de ~30 foi
atingido; o próximo crescimento exige tipo opaco de handle ou ADR que justifique a camada.
`os.cwd` segue fora: `std.paths` é lexical e não precisou dele.
Candidatas em avaliação na §13.9: `fs.open`/`net`, só com consumidor e ADR próprio.

### 13.5 Imports — pendências

Implementado em [ADR-0073](docs/adr/0073-imports-modulos.md): arquivo=módulo, pasta=namespace,
`_` privado, `from`/`as`, `std.` e desugar. Restam:

- [ ] Imports com caminho que sai da raiz (`..`) — decisão futura.

### 13.6 Batteries — concluídas

T1, T2 e T3 foram entregues (catálogo em [`docs/stdlib/`](docs/stdlib/)); não há módulo
pendente nesses tiers. `std.test`/`loxia test`, `std.property`, `std.rand`, `std.log`,
`std.hash`, `std.collections`, `std.timex` e os módulos de T1/T2 têm golden e página
gerada. Fora da stdlib continuam os itens do topo da §13 (regex, cripto, rede, async,
timezone DB, i18n, YAML/TOML, UUID, bigint) — [ADR-0072](docs/adr/0072-stdlib-batteries.md).

### 13.7 Ordem de entrega

| # | Passo | Esforço | Depende de |
| --- | --- | --- | --- |
| 1 | **Dogfooding**: portar `loxia fmt` para Lox (T3 concluída), com paridade byte a byte contra o Python ([ADR-0092](docs/adr/0092-estilo-e-formatter.md)) | L/XL | — |

### 13.8 Critério de pronto por módulo

Critério para qualquer módulo novo:

- programa real em `exemplos/` ou caso que o use (não simetria com outra linguagem);
- golden em `tests/cases/std_<modulo>.lx` + `--check` limpo;
- determinismo declarado (função ambiente ≠ corpus I1);
- doc pública em `std/*.lx` e página gerada em `docs/stdlib/`;
- zero sintaxe nova — se precisar, é ADR-0066, não stdlib;
- `make check` verde; `make bench` se tocar caminho quente.

### 13.9 Capacidades de host — `proc`/`poll` feitos; o resto não decidido

Origem: a pergunta "por que o LSP não dá em Loxia?". Resposta curta: o LSP local é
**stdio**, não rede ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)); o que falta de
kernel para isso é pequeno, e o bloqueio real é não haver front-end/checker chamável de um
programa Loxia. Análise completa em [`IDEIAS.md`](IDEIAS.md) I-11. `io.flush`/
`readUtf8` e `proc`/`poll` estão implementados ([ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md),
[ADR-0095](docs/adr/0095-processos-streams-poll.md)); `fs.open`/`net` seguem não
aprovados, e o servidor LSP continua em Python.

`byteLen(s)` e a coluna UTF-16 (o LSP conta UTF-16, não code points) continuam **Lox
puro** a fazer em `std/utf8` — não precisam de kernel e ainda não foram escritos.

**Candidatas depois (cada uma pede ADR próprio):**

| Camada | Superfície | Consumidor | Esforço |
| --- | --- | --- | --- |
| `fs.open` | `open(path, mode) -> File` (streaming, §10) | arquivos grandes, CSV/log | M |
| `net` | `tcpListen`/`tcpConnect`/`accept`/`close` (+ unix) | só com consumidor (HTTP client, debugger remoto) | M |

**Política mínima (se entrar):** tudo `ambient: true` (fora do I1/I3); erro de host em
`Result[T, OsError]`, não `T?`; handle opaco com `close()` explícito e sem finalizer
(Boehm não é determinístico); `poll` **antes** de thread; nenhum callback C→Lox que possa
lançar; sem FFI genérica (`extern fn` continua fora, ADR-0071); `net` v1 só com IP
literal, sem DNS nem TLS.

**Ordem sugerida:** `fs.open` (M) → `net` (L, só com dor). O servidor LSP continua em Python
([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)) — não reabrir.

**Orçamento de kernel:** 29 de ~30; crescer daqui pede tipo opaco de handle e ADR.

---

## 14. Publicação e ecossistema

Fora da fila de features (§0): nada aqui muda a linguagem, então não passa pelo portão do
ADR-0014. A ordem importa por dependência real — URL e CI estáveis antes do site, e a spec
consolidada antes do MCP, que a consome.

| # | Entrega | Por que nesta ordem |
| --- | --- | --- |
| 1 | {@14.1} Repositório público | é o pré-requisito de URL, issues e release |
| 2 | {@14.2} Documentação como site | depende do repo público e do CI |
| 3 | {@14.3} Servidor MCP | depende da spec publicada e estável |
| 4 | {@14.4} Distribuição, stdlib instalada e pacotes | **pré-requisito técnico** do release da §14.1: resolução de módulos/pacotes e `uv build`/sdist; wheel e comando já prontos |
| 5 | {@14.5} Corpus de conformidade como artefato | em paralelo; depende do manifesto estabilizado (já está) |
| 6 | {@14.6} Primeiro programa real e docs de usuário | depende de 4 (instalar) e alimenta a §14.2 (tutorial/cookbook) |
| 7 | {@14.7} CLI único e gerenciador de pacotes | fase 0 junto da 4; fases 1–2 depois do release; fase 3 só com demanda |

### 14.1 Abrir o repositório

Hoje existem `LICENSE`, `README` e um workflow de CI; falta o "contrato social" de um repo
público e a automação de suprimentos.

- **Comunidade:** `CONTRIBUTING.md` (rodar da raiz, `make check`, Conventional Commits,
  resumo dos portões do [ADR-0014](docs/adr/0014-identidade-e-invariantes.md) e do
  [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md)), `CODE_OF_CONDUCT.md`
  (Contributor Covenant), `SECURITY.md` (o que é vulnerabilidade aqui: crash/panic no
  interpretador ou no backend, escape do sandbox do `--emit` — bug de semântica é issue,
  não CVE) e `GOVERNANCE.md` só quando houver segundo mantenedor.
- **Templates:** `.github/ISSUE_TEMPLATE/bug.yml` (versão, saída de `--version`, caso mínimo
  `.lx`), `feature.yml` (exige as quatro perguntas do ADR-0066 — filtro barato contra pedido
  de sintaxe) e `PULL_REQUEST_TEMPLATE.md` com o DoD do `AGENTS.md` §7.
- **Dependabot** (`.github/dependabot.yml`): `uv` (dev-deps), `github-actions` e `pip`,
  agrupado semanal; ignorar major de `llvmlite` (acoplado ao LLVM).
- **Endurecer CI:** `permissions: read-all` no topo do workflow, `contents: write` só no job
  de release, ações pinadas por SHA (cadeia de suprimentos) e CodeQL para Python (CLI/interpretador)
  e C (`runtime/*.c`, header comum `runtime/lox_runtime.h`); o código gerado não entra.
- **Release:** workflow em tag `v*` → `uv build`, anexar wheel/sdist no GitHub Release e
  publicar no PyPI via **Trusted Publishing** (OIDC, sem token). Depende de reservar `loxia`
  no PyPI (hoje livre).
- **Higiene:** `.gitattributes` (`* text=auto eol=lf`), `.editorconfig`, badges no README
  (CI, versão, licença) e conferir `.gitignore` (`.tmp-*`, `.uv-cache`, shim de `gc.h`) no
  primeiro clone público.
- **Custo/risco:** público significa issue e PR de estranho; sem `CONTRIBUTING` a triagem
  vira ruído. E publicar **congela** API — por isso o [ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md)
  veio antes.

### 14.2 Documentação como site (+ i18n)

Princípio: o site é **build** de `docs/`, nunca fonte paralela. O front matter `sources:` de
`docs/spec/*.md` dá de graça o diferencial que linguagem pequena não costuma ter: cada
página declara "verificado no commit X", reusando `docs/_hooks/freshness.py`.

- **Stack:** Astro Starlight (mais perto da UX do site do Kotlin: sidebar, busca local, i18n
  por pasta, dark mode) ou VitePress. Alternativa que não soma toolchain JS: MkDocs
  Material, que é Python e casa com o resto do repo. **Decisão pendente:** dois ecossistemas
  vs. um.
- **Estrutura:** `/learn` (tutorial de 30 min), `/reference` (gerado da spec), `/stdlib`,
  `/cookbook` (de `exemplos/`), `/why` (I1–I4 em uma página) e `/changelog`. ADRs ficam fora
  do site — são registro interno; linkar só o índice.
- **i18n:** a spec e os ADRs são pt-BR. Recomendação: pt-BR é a fonte; en-US traduz apenas
  *learn* e *reference*; ADRs não são traduzidos. A **API pública** (stdlib/builtins) tem
  doc em inglês ([ADR-0091](docs/adr/0091-doc-comments-e-geracao-de-docs.md)); o site marca
  `/stdlib` como inglês e o resto como pt-BR até a tradução. Tradução congela texto, então
  cada página traduzida precisa do mesmo mecanismo de frescor, senão o inglês apodrece
  primeiro.
- **`/stdlib` e builtins gerados:** `loxia doc` (ADR-0091) gera Markdown/JSON a partir de
  `///` e do registry de primitivas; o site **consome** o gerado, não edita à mão. O build
  falha se a referência estiver defasada.
- **Playground:** o alvo é WASM (§6.10). Até lá, ou playground server-side (`run`/`--check`
  com timeout e sem rede), ou nenhum — não vale um serviço só para enfeite.
- **Gate:** `make docs-build` no CI (links quebrados, front matter inválido, página sem par
  traduzido). O `tests/test_docs_links.py` continua sendo o portão da fonte.

### 14.3 Servidor MCP (`loxia-mcp`)

Objetivo: um agente (Claude/Codex/DSH) escrever Loxia **que compila** e ler a spec sem
alucinar. O projeto está pronto de um jeito incomum: `--error-format=json` já devolve
envelope versionado (`schema_version`, `code`, `phase`, `span`) e o I3 garante os mesmos
bytes — diagnóstico determinístico é exatamente o que tool de agente precisa.

O contrato do CLI que o MCP consome é o do
[ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md): subcomandos, `capabilities`,
`explain`, JSONL/watch e exit codes estáveis. O MCP não reimplementa diagnóstico.

- **Tools:** `loxia_check(source)` → diagnósticos; `loxia_run(source, args, timeout_ms)` →
  stdout/stderr/exit; `loxia_ast(source)` → S-expression; `loxia_spec(query)` → trechos de
  `docs/spec/` (índice/grep determinístico, sem embeddings); `loxia_explain(code)` →
  descrição do catálogo ([ADR-0075](docs/adr/0075-diagnosticos-estruturados.md));
  `loxia_version()`; opcional `loxia_repl(session, line)`.
- **Grammar pronta:** `editors/shiki/loxia.mjs` (Shiki genérico) e `editors/dsh/loxia.ts`
  (viewer do harness, cópia manual); ambos gerados por `make grammar`, com o patch de
  3 pontos descrito em [`editors/README.md`](editors/README.md).
- **Resources:** `spec://lexico|sintaxe|semantica|erros|garantias`, `adr://NNNN`,
  `example://fib`. **Prompts:** "corrija este erro", "escreva uma função com contrato".
- **Dependências:** SDK `mcp` só no extra `[mcp]`; o runtime segue sem dependências.
  Transporte stdio (local); HTTP/SSE só com caso de uso hospedado.
- **Segurança:** `loxia_run` é execução de código arbitrário → timeout, sem rede, fs
  read-only, cap de pilha ([ADR-0077](docs/adr/0077-limite-de-pilha.md)) e de memória
  ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)); `--emit=exe` negado por
  padrão.
- **Contrato:** toda tool devolve os **mesmos bytes** do CLI correspondente, com teste de
  paridade CLI×MCP — o MCP é camada fina sobre o CLI, não reimplementação. Fixar a versão do
  protocolo: a especificação do MCP muda rápido.
- **Não fazer:** MCP que gera código por conta própria, RAG com embeddings (não
  determinístico) e tool que edita arquivo do usuário.

### 14.4 Distribuição, stdlib instalada e pacotes externos

**O que ainda falta.** O item 1 fechou wheel, entry point, bundle de `std/`/`runtime/` e
teste de instalação. O gap restante é **resolução de módulos e dependências**:

- a raiz de módulos é o diretório do arquivo de entrada; `..` e caminho absoluto são erro
  ([ADR-0073](docs/adr/0073-imports-modulos.md)). Um projeto ainda **não consegue** consumir
  código fora da própria pasta — nem dependência, nem monorepo;
- `std.*` é raiz reservada e resolve no bundle; o loader **inlina** os módulos em
  compile-time, então tree-walk e backend usam a mesma resolução (bom: um caminho só);
- `loxia.toml`/`[modules]` e `loxia.lock` ainda não existem no fluxo de pacotes.

**O que isso custa hoje.** Instalar já funciona; o primeiro usuário que tentar `import` de
um pacote vai bater na regra do `..`. É o maior *gap* entre "projeto impressionante" e
"ferramenta" — e depende de decisão de design, não de feature.

**Item 1 — empacotar e instalar (sem decidir resolução ainda).**

> Dívida do ADR-0088 **resolvida** em 2026-11-15: `src/` virou `loxia_core/`; o wheel
> não instala mais um pacote top-level chamado `src`.

Empacotamento e instalação já funcionam: wheel com `std/`/`runtime/`, entry point
`loxia`, subcomandos `run|check|build|ast|fmt|doc|explain|capabilities|lsp|test|fix` e
`tests/test_install.py` (wheel em venv fora do repo). Resta:

- [ ] `uv build` e sdist sem `std/` duplicado; `CHANGELOG`/README com o comando de
      instalação.

**Item 2 — resolução de módulos e pacotes (decidido no
[ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md); desenho e opções em
[`IDEIAS.md`](IDEIAS.md) I-9).**

- [ ] Raízes ordenadas e determinísticas: `projeto` → raízes declaradas no manifest →
      `std` (reservada, sempre por último).
- [ ] `loxia.toml` com `[package] name` e `[modules] paths`; resolver `import acme.foo` pelo
      pacote declarado, não pelo nome do diretório.
- [ ] Política do `..`: **proibido no statement `import`** (mantém a regra), permitido apenas
      como raiz declarada no manifest — monorepo funciona, fonte nunca escapa da raiz.
- [ ] Ambiguidade entre raízes = erro explícito (nunca "primeira vence" em silêncio).
- [ ] Determinismo: sem variável de ambiente; ordem fixa; diagnóstico lista raízes
      **relativas** ao projeto (I3); `std` não pode ser sombreado.
- [ ] Testes: monorepo com `../shared` declarado; raiz ambígua; pacote instalado; `std`
      reservado; wheel de fora do repo.

**Não fazer agora:** registry com rede, resolução de versões/semver, pacote binário e
`../` dentro do fonte. Um gerenciador de pacotes completo é outro produto; o mínimo é
"dependência declarada + resolução determinística".

### 14.5 Corpus de conformidade como artefato

O que viaja não é a linguagem — é o **corpus**. Hoje ele já é maduro: casos `.lx`
autoexplicativos, manifesto por nível, promoção monotônica, runner diferencial nos três
canais.

- [ ] Extrair `conformance/` (ou repo próprio): casos anotados, manifesto, runner e README
      que explique o contrato (`# expect:`, `PENDING`, `NEGATIVE`).
- [ ] Duas camadas: **`lox-core`** (subconjunto compatível com o livro, para quem implementa
      jlox/clox) e **`loxia`** (dialeto: `val`/`var`, `fn`, `print(...)`, enums, etc.).
      Sem essa separação o corpus só serve a nós.
- [ ] Runner genérico: `conformance run --impl "<comando>"` roda qualquer interpretador e
      compara stdout/stderr/exit, sem depender do nosso CLI.
- [ ] Licença: conferir a da suíte oficial (`tests/official/LICENSE`) e declarar a dos casos
      nossos.
- [ ] README com o mapeamento de divergências (o que um implementador do livro precisa
      mudar para rodar a camada `lox-core`).

**Por que vale:** precedente é WebAssembly spec tests/Test262 — quem implementa uma linguagem
usa os testes de outra. É uma contribuição à comunidade Lox que **não exige adotar a Loxia**,
e resolve o problema de "mais uma linguagem" na base da utilidade. É também a melhor
vitrine técnica do projeto: o corpus é o que prova I1.

### 14.6 Posicionamento, primeiro programa real e docs de usuário

**A escada da singularidade.** Feature se copia num fim de semana; propriedade não:

| Nível | O que é | Estado |
| --- | --- | --- |
| feature | `??`, `match`, generics | emprestado, e deve continuar assim |
| **propriedade** | dois motores obrigados a concordar byte a byte + contratos de recurso + manifesto público | ✅ é o que existe de único |
| **nicho** | "a linguagem para X" | ⬜ ainda não escolhido |

**Métricas melhores que "adoção".** (1) você usa a Loxia todo dia para algo que te dá
valor; (2) um artefato seu é usado por outra pessoa (o corpus, §14.5); (3) self-hosting.
Adoção ampla não é meta de projeto solo — é consequência improvável de uma dessas três.

- [ ] **Um programa real**, com `std.csv`/`std.json`/`std.fs`/`std.cli`: algo que você
      realmente use (relatório CSV→HTML/JSON, analisador de logs, gerador de site). Publicar
      o **programa** e um texto curto de "por que escrevi isso em Loxia".
- [ ] Tutorial de 30 min (base do `/learn` da §14.2) e cookbook a partir de `exemplos/`.
- [ ] Página "por que Loxia": os três casos de uso reais + I1–I4 + orçamentos, em uma
      página; sem comparação com Python/Kotlin que não seja "para este caso, aqui".
- [ ] Transparência: o README e os ADRs já dizem "Cássio + agente"; manter isso declarado,
      sem liderar com o assunto. O post técnico é sobre o harness/contratos — o artefato
      fala por si.

**Não fazer:** caçar aprovação de comunidade que rejeita o método de construção; anunciar
a linguagem antes de existir um programa real; medir sucesso por estrelas.

### 14.7 CLI único e gerenciador de pacotes (fases)

Objetivo: **um** comando (`loxia`) que roda, compila, testa e resolve pacotes — sem um
segundo nome. A análise completa (o que o `uv` resolve que a Loxia não tem, requisitos,
não-objetivos) está em [`IDEIAS.md`](IDEIAS.md) I-10; aqui fica o que fazer.

- [ ] **Fase 0 — restante do CLI único** (junto da §14.4): `loxia repl` como subcomando;
      `run|check|build|ast|fmt|doc|explain|capabilities|lsp|test|fix` já existem e as flags
      atuais continuam aceitas ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)).
- [ ] **Fase 1 — manifest + lock** (`loxia.toml` já existe pelo [ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md)):
      `[dependencies]`, `loxia.lock` com versão exata + `sha256`, `loxia lock`,
      `loxia fetch --offline` e cache local. Critério de pronto: dois manifests iguais com o
      mesmo lock produzem a mesma árvore de raízes e o mesmo build; `loxia run` funciona
      offline.
- [ ] **Fase 2 — path e git**: `dep = { path = "../lib" }` e `dep = { git = "...", rev = "..." }`.
      Resolve monorepo sem registry. Critério: monorepo real em `exemplos/` compila nos dois
      motores.
- [ ] **Fase 3 — índice estático**: índice *sparse* (JSON por pacote) + tarball por versão +
      `loxia add nome@1.2`. **Só entra com demanda de terceiro**; hospedar é barato, moderar
      nome não.
- [ ] **Fase 4 — resolver em Loxia**: dogfooding do resolver na própria linguagem (como
      Cargo em Rust), depois do self-hosting; exige `sha256` como primitiva do kernel.

**Não fazer:** registry antes de demanda, semver completo com backtracking antes de pacote
real, scripts de build em pacote (risco de supply chain), pacote binário, mirrors.

### 14.8 Divisão de repositórios (organização `loxia-lang`)

**Regra:** separa quem **consome artefato**; não separa quem **compartilha invariante**.

| Fica no repo principal | Por quê |
| --- | --- |
| `loxia_core/` + `loxia/` | são o produto; I1/I3 e a spec vivem aqui |
| `runtime/*.c` | ABI do backend (6 unidades por domínio + header); `driver.py` compila e linka junto |
| `std/` | package data, versão = versão do compilador, resolvida pelo loader |
| `docs/spec/`, ADRs, `docs/_hooks/` | frescor (`sources:`) e links apontam para o código |
| `tests/` (casos + manifesto + diferencial) | é o corpus do I1; teste não pode depender de fetch |
| `exemplos/`, `bench/` | rodam na suíte |

| Repo próprio | Quando | Dependência |
| --- | --- | --- |
| `loxia-editors` (VS Code + Shiki) | ao publicar no Marketplace | **cliente**: grammar gerada no principal + empacotamento da extensão; sem semântica |
| `loxia-lsp` | **não separar agora** — ver abaixo | consome `Checker`/`AST`/`SourceMap` direto; contrato de diagnóstico versiona junto |
| `loxia-mcp` | quando o MCP existir (§14.3) | CLI como caixa-preta, versão pinada |
| `loxia-conformance` | no primeiro release público | **espelho gerado** do corpus, nunca fonte de verdade |
| `loxia-site` | quando o site virar build próprio (§14.2) | consome `docs/` do principal |
| `loxia-playground` | com o alvo WASM (§6.10) | compilador como artefato |
| `loxia-bench` | só se a suíte virar pública | baseline acoplado à versão |

- [ ] Criar `loxia` (principal) na org e mover o repo antes de qualquer split.
- [ ] `.github` da org com README/perfil, templates e política de segurança comuns.
- [ ] Extrair `loxia-editors` com `git subtree split -P editors` (preserva histórico).
- [ ] CI do principal publica `syntaxes/loxia.tmLanguage.json` como release asset; o repo de
      editores consome (nunca copiar à mão).
- [ ] `loxia-conformance` gerado por script a partir de `tests/cases` + manifesto.
- [ ] Tap do Homebrew (`homebrew-loxia`) só quando houver binário de release.

**LSP: cliente × servidor.** A assimetria com o MCP é o critério:

- **MCP** é cliente do **CLI** (caixa-preta, `--error-format=json`): pode morar fora.
- **LSP** é consumidor dos **internos** (AST, checker, spans, `SourceMap`): fica no
  principal, como `loxia lsp` (ou entry point `loxia-lsp`), em **Python com JSON-RPC à mão**
  ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)). O trabalho real do LSP é o
  modelo de diagnóstico do [ADR-0075](docs/adr/0075-diagnosticos-estruturados.md), que
  versiona junto com o compilador; separar criaria duas releases por mudança de span/código.
  O LSP não é escrito em Loxia: não há processo/servidor nem front-end self-hosted que o
  programa Loxia possa consultar.
- O repo `loxia-editors` fica só com o **cliente** (extension manifest, grammar, packaging).
- Contrato: o servidor responde em processo, mas o mesmo resultado tem que sair de
  `loxia check --error-format=json` — teste de paridade, como no MCP.
- **Gatilhos para separar:** dependência própria (se algum dia adotada; hoje o
  [ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md) decide JSON-RPC à mão, sem
  `pygls`/`lsprotocol`), cadência de release dirigida por clientes de editor, ou um segundo
  mantenedor. Até lá, separar só paga o custo de sincronizar dois relógios.

**Não fazer:** abrir 6 repositórios antes do primeiro release (custo de CI/versão/
sincronização sem consumidor); mover `std/` ou `runtime/` para fora (drift de ABI/versão);
duplicar a spec; separar o LSP para "ficar organizado" sem consumidor próprio.
