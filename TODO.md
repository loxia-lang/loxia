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

> Regra de ouro: fechar as definições que cada nível consome **antes** de codá-lo
> (checklist na §0.1). Cada feature nova entra com teste; cada mudança de sintaxe entra
> documentada no mesmo commit.

---

## 0. Fila única

Esta é a **ordem oficial**. As seções 1–12 são o catálogo de detalhes; se houver conflito,
vale o que está aqui. Estado em 2026-11-15: **L0–L6, L7, M7, T1 e T2 concluídos**; kernel
v1 (17 primitivas), tabela de primitivas, imports/módulos e a stdlib comum implementados.
Pilha ([ADR-0077](docs/adr/0077-limite-de-pilha.md)) e heap
([ADR-0087](docs/adr/0087-heap-cap-e-self-hosting.md)) estão fechados; a próxima execução
é **diagnósticos** (§0.2). O status por nível é **gerado** em
[`docs/spec/garantias.md`](docs/spec/garantias.md) a partir de
[`tests/corpus_manifest.py`](tests/corpus_manifest.py) — não copie números para cá.

### 0.1 Definições que não podem faltar antes de cada nível

| Antes de | O que precisa estar fechado | Estado |
| --- | --- | --- |
| **L6** | enums/`match`, exceções, `Any` e corpus completo | ✅ |
| **L7** | `mod.verify()`, `-O2`, benchmark nativo, erros de codegen | ✅ (JIT no REPL é P3 separado) |
| **M7** | GC Boehm + contrato de memória do [ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md) | ✅ implementado |
| **T1** | `std.strings`, `std.lists`, `std.maps`, `std.numeric`, `std.asserts`, `std.results` sobre módulos/imports | ✅ concluído |
| **T2** | `std.{json,fmt,paths,fs,io,cli,sets,csv,convert}` sobre o kernel T2 ([ADR-0079](docs/adr/0079-stdlib-t2.md)) | ✅ concluído |

### 0.2 Ordem de execução

1. [x] **T1 — stdlib núcleo**: `std.strings`, `std.lists`, `std.maps`, `std.numeric`,
       `std.asserts` e `std.results`; cada módulo com golden, `--check` e determinismo.
2. [x] **T2 — stdlib comum**: `json`, `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv`,
       `convert` ([ADR-0079](docs/adr/0079-stdlib-t2.md)).
3. [x] **Limite de pilha**: [ADR-0077](docs/adr/0077-limite-de-pilha.md) implementado
       (10.000 chamadas, orçamento de 64 MiB, `R1015`).
4. [x] **Heap**: [ADR-0087](docs/adr/0087-heap-cap-e-self-hosting.md) implementado
       (default 512 MiB + `--max-heap` de build).
5. [ ] **Diagnósticos**: fonte de módulo no checker entregue; falta stack trace de
       runtime (com a fonte do módulo nos frames, inclusive no nativo).
6. [ ] **JIT no REPL** (`P3`): desenho próprio antes de codar; não bloqueia stdlib.
7. [ ] **M8/M9**: performance restante e ecossistema (formatter, LSP, playground).

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

- [ ] **Stack trace de runtime** (`P2`): frames `at f (linha N) ← main (linha M)`; no
      binário, decidir o custo de carregar frames. O limite de pilha já existe
      ([ADR-0077](docs/adr/0077-limite-de-pilha.md)); `R1015` ainda não tem posição.
- [ ] **`notes` de proveniência** (`P2`): "o valor vem de `pessoa.nome` (linha 7)" exige
      spans de expressão no checker, não só o token.
- [ ] **`fixes[]`** (`P3`): `applicability` + `edits[]` por span; só quando houver edição
      confiável (um `fix` errado é pior que nenhum).
- [ ] **`lox explain <code>`** e **`lox capabilities --json`** (`P3`): dependem de
      subcomandos no CLI.
- [ ] **`--json-lines`** (`P3`) e `--timeout` para execução.
- [ ] **Warnings** e `-Werror` (`P3`): o modelo tem `severity`, mas nenhum produtor ainda.
- [ ] **LSP** (`P3`): reusar o mesmo `Diagnostic` em `textDocument/publishDiagnostics`.

**Anti-metas:** não imprimir direto do scanner/parser (só coletar); não usar `assert` do
Python para validar código do usuário; não classificar código por prefixo de mensagem.

### 6.9 CLI alvo

```bash
lox run script.lx            # interpretador (hoje: main.py script.lx)
lox check script.lx          # só typecheck/resolver (hoje: --check)
uv run main.py --emit=ll  script.lx  # inspecionar LLVM IR (hoje)
uv run main.py --emit=obj script.lx  # .o para linkar (hoje)
uv run main.py --emit=exe -o app script.lx  # nativo (hoje)
lox build script.lx -o app   # nativo (quando o CLI ganhar subcomandos)
lox build script.lx --emit=ll        # equivalente futuro
lox jit script.lx            # MCJIT, sem arquivo intermediário
lox fmt script.lx            # formatador (dogfooding do parser)
lox repl                      # REPL, com :type, :ast
```

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

- [x] `P2` testes diferenciais interpretador × LLVM no corpus anotado (`LEVELS`; PENDING 0).
- [ ] `P2` CLI agent-friendly: `--json` em `check`/`ast`/`types`/`fmt`, `--no-progress`,
      `--timeout`, sem prompt interativo, exit codes estáveis (checklist em
      [`IDEIAS.md`](IDEIAS.md) I-4).
- [ ] `P3` fuzzing do scanner/parser com `hypothesis`.
- [ ] `P3` snapshot de AST em arquivo.
- [x] `P3` grammar TextMate + extensão VS Code em `editors/`, gerada de `keywords.py`
      (`make grammar`), com teste de drift.
- [ ] `P3` tree-sitter grammar + LSP mínimo (diagnostics/hover).
- [ ] `P3` `lox fmt` e teste de idempotência.
- [ ] `P3` site publicado a partir de `docs/` — ver §14.2 (stack, i18n e gate).
- [ ] `P3` servidor MCP (`loxia-mcp`) — ver §14.3; depende do CLI agent-friendly acima.

---

## 8. Lox2: o que ainda vale

| Recurso | Status | Nota |
| --- | --- | --- |
| iterador de usuário no `for-in` | ✅ | protocolo estrutural `iter()` + `next() -> T?`, classe/interface/genérico; caso no diferencial ([ADR-0082](docs/adr/0082-iterador-de-usuario.md)) |
| `print` como função | ✅ | `print(valor): Any -> Nil`, statement removido; corpus/suíte oficial exemplos migrados ([ADR-0085](docs/adr/0085-print-como-funcao.md)) |
| variádicos `...args` | ✅ | `...xs: T` + spread final `f(...xs)`; `fmt.format` migrado ([ADR-0083](docs/adr/0083-variadicos.md)) |
| `type` alias | ✅ | `type Nome = Tipo` transparente, não-genérico, módulos e backend ([ADR-0084](docs/adr/0084-type-alias.md)) |
| generics + constraints | ✅ | funções T3b + `T: Ord + Num + Interface` ([ADR-0081](docs/adr/0081-constraints-generics.md)); constraints em classes seguem pós-MVP |
| uniões + narrowing | ✅ | `T?`/`is`/`while`/campos/índices, merge de ramos e `var` capturado ([ADR-0086](docs/adr/0086-narrowing-captura-e-merge.md)); aliasing/CFG completo fora |
| interfaces nominais + `implements` | ✅ | item "traits" do Lox2: tree-walk/checker + backend B2 (`itab`), dois casos no diferencial ([ADR-0080](docs/adr/0080-interfaces-nominais-implementacao.md)) |
| namespaces/import | ✅ | [ADR-0073](docs/adr/0073-imports-modulos.md): arquivo=módulo, `_` privado, `std.*` e `from`/`as` |
| `try`/`raise` no backend | ✅ | tree-walk e backend L6 ([ADR-0042](docs/adr/0042-excecoes.md), [ADR-0062](docs/adr/0062-l6-excecoes-unwinding.md)) |
| FFI com C | ⏸ | **não haverá FFI genérica**: kernel fixo de primitivas ([ADR-0071](docs/adr/0071-primitivas-de-runtime.md)); reavaliar só com dor demonstrada |
| stdlib (`strings`, `lists`, `collections`) | 🟡 | kernel e imports prontos; T1/T2 na §13 ([ADR-0072](docs/adr/0072-stdlib-batteries.md)) |
| `async`/`await` | ⏳ | direção no [ADR-0037](docs/adr/0037-async-direcao.md): colored, `Task[T]`, determinístico; só com I/O, pós-M7 |

Fora: VM própria, GC geracional, JIT tracing, cache de bytecode e `Object` raiz — o LLVM
cobre o codegen e o escopo humano manda.

---

## 9. Milestones pendentes

M0–M7 estão fechados (ver [`docs/decisoes.md`](docs/decisoes.md)). Falta:

| # | Marco | Critério de pronto | Estado |
| --- | --- | --- | --- |
| **M8** | Performance | `-O2` e benchmarks feitos; JIT no REPL é P3 e não bloqueia | 🟡 |
| **M9** | Ecossistema | formatter, LSP, docs e playground | ⬜ |

**Regra:** a ordem oficial é a §0. Se algo mudar a semântica de um nível já compilado, o
nível afetado volta para a fila com caso diferencial. Interfaces nominais estão
implementadas (ADR-0080), constraints de função também (ADR-0081) e iteradores de usuário
no `for-in` (ADR-0082) — nenhum bloqueia nível.

**Async (ADR-0037):** a arquitetura (frames materializáveis, GC que enxergue frames
suspensos) é preparada durante o L6; a feature entra **depois do M7**, junto com a stdlib
de I/O, e **antes do M8**. Sem I/O não há o que esperar e a feature não passa no portão do
ADR-0014. Paralelismo/multithread fica em avaliação no [`IDEIAS.md`](IDEIAS.md) — não é
async.

### 9.1 Divergências I1 conhecidas (fora do corpus)

Achadas ao implementar o [ADR-0075](docs/adr/0075-diagnosticos-estruturados.md) e
corrigidas com regressão no diferencial de `tests/test_backend.py`. Hoje não há
divergência I1 conhecida fora do corpus. Limite declarado (regra da
linguagem, não do lowering): `is`/`as` com argumentos de tipo em classe/enum é recusado pelo checker (`E3000`) e o tree-walk levanta `R1014`.


---

## 10. Parque de diversões (ideias soltas)

- [ ] **Compilar o próprio interpretador?** (self-hosting) — o *front-end* já é
      self-hostable hoje (lexer em Lox compila nativo e bate a saída); o compilador inteiro
      depende de I/O, GC e do resto do L6. Escada em §13.7 (passo 7). P3/XL.
- [ ] **`lox fmt` em Lox** — primeiro exercício de dogfooding depois do kernel: parser +
      AST printer na própria linguagem, validado contra o `--dump-ast` do Python (§13.7).
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
        para CSV/logs grandes e para o `lox fmt`/self-hosting.
- [ ] **Playground WASM** (target `wasm32` do LLVM) rodando no navegador.
- [ ] **REPL com `:type`** — mostra o tipo inferido de uma expressão antes de rodar.
- [ ] **`lox test`** — runner de testes embutido na linguagem (`#[test] fn ...`).
- [ ] **Erros com sugestão** ("você quis dizer `println`?" via distância de edição).
- [ ] **Debugger (DAP)** — breakpoints no tree-walk primeiro; no nativo depois.
- [ ] **Hot reload** no REPL (redefinir funções sem perder estado).
- [ ] **Benchmark suite pública** (fib, nbody, mandelbrot) para acompanhar regressões.
- [ ] **Compilar para um Arduino/Pico?** (LLVM target `thumbv6m`) — suicídio de escopo,
      mas divertido de tentar um dia.
- [ ] **Dialeto embutido**: `lox` como linguagem de script de um app Python (via CFFI).
- [ ] **Gerador de AST a partir de schema** (o livro faz à mão; um script evita erro
      quando a linguagem crescer).
- [ ] **`lox doc`** — gera docs a partir de comentários de documentação (ex.: `##`).

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
2. **Stdlib pós-1.0:** `io`, `string`, `collections`, `time` não determinístico;
   transcendentais de `math` fora do I3.
3. **Interfaces genéricas e constraints em classes:** `interface I[T]` e
   `class C[T: I]` continuam em aberto; constraints de função já existem
   ([ADR-0081](docs/adr/0081-constraints-generics.md)).
4. **Contratos e agentes:** `requires`/`ensures`/`invariant`, `--contracts` default e JSON
   schema v1 com `fixes[]` — [`IDEIAS.md`](IDEIAS.md) I-4.
5. **`if`/bloco como expressão:** fora da 1.0; reavaliar quando houver dor real.
6. **Paralelismo (multithread):** em avaliação no [`IDEIAS.md`](IDEIAS.md); async é
   concorrência single-thread ([ADR-0037](docs/adr/0037-async-direcao.md)), não paralelismo.
7. **HIR-lite — gate explícito:** não construir agora. Trocar para HIR-lite só se um
   destes gatilhos disparar ([ADR-0065](docs/adr/0065-hir-lite-controle.md)):
   `lower_exceptions.py`/`lower_enums.py` passarem de ~350 linhas, o lowering precisar de
   mais de 2 níveis manuais de blocos/phi, ou uma feature exigir CFG explícito (stack
   trace com frames, cleanup dinâmico completo, JIT). `Any` e containers sozinhos não
   disparam.
8. **Cleanup de exceções:** `finally` cobre o corpus; cleanup dinâmico completo em
   `raise` através de frames aninhados é dívida declarada, não bloqueia a stdlib.
9. **Imports:** [ADR-0073](docs/adr/0073-imports-modulos.md) implementado; resta `..`
   fora da raiz. Diagnóstico de checker com a fonte do módulo está feito
   (`Token.file`); o runtime ainda fica no arquivo da entrada até o frame stack (§3.1).

> Nome e extensão saíram daqui: **Loxia** e `.lx`, decididos no
> [ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md).

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

> **Escopo:** pós-1.0; **não** bloqueia L6/L7 (§0.2). O kernel v1 vem **depois do GC**
> ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)). Decisões:
> [ADR-0071](docs/adr/0071-primitivas-de-runtime.md) (primitivas e complexidade),
> [ADR-0072](docs/adr/0072-stdlib-batteries.md) (política de batteries) e
> [ADR-0073](docs/adr/0073-imports-modulos.md) (imports — **implementado**).
>
> **Regra de ouro:** kernel = SO ou representação; tudo o mais é Lox. Nenhuma lógica de
> negócio em primitiva, nenhuma primitiva que Lox faria em O(n).
>
> **Fora:** regex, cripto, rede, subprocesso, async, timezone DB, i18n, YAML/TOML, UUID, bigint.

### 13.1 Camadas

| Camada | O que entra | Implementações | Onde |
| --- | --- | --- | --- |
| kernel | syscalls e representação | Python (oráculo) + C (binário) | `loxia_core/execution/primitives.py`, `runtime/runtime.c` |
| std | biblioteca | **uma** (Lox) | `std/*.lx` |
| módulos | nomeação e carga | loader/desugar, sem lógica | `loxia_core/loader/` |

**Kernel concluído** com **17** primitivas: `args`, `io.*` (incluindo `readAll`), `fs.*`
(`exists`, `listDir`), `os.*`, `time.*`, `substr`, `join`, `charCodeAt`, `fromCodePoint`.
O teto subiu de 15 para 17 na T2 ([ADR-0079](docs/adr/0079-stdlib-t2.md)); o critério
continua sendo SO ou representação, e qualquer crescimento novo exige ADR. `os.cwd`
segue fora: `std.paths` é lexical e não precisou dele.

### 13.2–13.3 Kernel v1 e complexidade — concluídos

Kernel de SO (13.2) e cache de code points/`substr`/`join`/`charCodeAt`/`fromCodePoint`
(13.3) estão implementados e cobertos por `k0`, `tests/test_kernel.py` e
`bench/cases/string_scan.lx`. O detalhe fica no [ADR-0071](docs/adr/0071-primitivas-de-runtime.md);
não repetir a tabela aqui.

### 13.4 Tabela única de primitivas

Tabela implementada para as primitivas monomórficas. Migrar `len`/`chars`/`str`/`repr`/
`range` é **opcional**: não muda performance (são builtins especiais) e melhora a
arquitetura só quando reduzir casos especiais no checker/lowering; não bloqueia T1.

### 13.5 Imports — pendências

Implementado em [ADR-0073](docs/adr/0073-imports-modulos.md): arquivo=módulo, pasta=namespace,
`_` privado, `from`/`as`, `std.` e desugar. Restam:

- [ ] Imports com caminho que sai da raiz (`..`) — decisão futura.
- [ ] Diagnóstico de checker com fonte do módulo (hoje aponta o entry).

### 13.6 Batteries — inventário

Tiers do ADR-0072. `⬜` = a fazer; cada módulo entra com golden + `--check` + auditoria de
determinismo.

**T0 — kernel** (13.2): concluído; a base de tudo.

**T1 — núcleo**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.strings` | ✅ base: `split`, `splitLines`, `lines`, `words`, `trim`, `ltrim`, `rtrim`, `upper`, `lower` (ASCII), `capitalize`, `startsWith`, `endsWith`, `contains`, `indexOf`, `lastIndexOf`, `replaceAll`, `replaceFirst`, `repeat`, `padStart`, `padEnd`, `reverse`, `slice` (clamp), `isBlank`, `count` | ✅ base completa |
| `std.lists` | `map`, `filter`, `each`, `fold`, `reduce`, `find`, `findIndex`, `any`, `all`, `none`, `count`, `sum`, `min`, `max`, `sort`, `sortNatural`, `reverse`, `slice`, `take`, `drop`, `zip`, `flatten`, `unique`, `contains`, `indexOf`, `first`, `last`, `getOr`, `chunk`, `partition`, `flatMap` | ✅ base + sort/gaps; `min`/`max` são `[T: Ord]`, `sortNatural` é novo; `sortBy`/`groupBy` adiados ([ADR-0076](docs/adr/0076-std-lists-sort.md), [ADR-0081](docs/adr/0081-constraints-generics.md)) |
| `std.maps` | `entries`, `fromEntries`, `merge`, `pick`, `omit`, `mapValues`, `filterKeys`, `filterValues`, `invert`, `hasValue`, `getOr`, `toList` | ✅ `Map[String, V]`; `invert` é `Map[String, String]` (constraints de chave genérica pós-MVP) |
| `std.numeric` | `gcd`, `lcm`, `isPrime`, `primes`, `factorial`, `powMod`, `digitSum`, `isEven`, `isOdd`, `sign`, `mean`, `median`, `mode`, `variance`, `stddev`, `roundTo`, `toBase`, `fromBase` | ✅ estatísticas de `List[Int]`, vazio ⇒ `nil`; domínio inválido ⇒ `LoxRuntimeError` |
| `std.asserts` | `assert`, `assertEq`, `assertNotNil`, `fail` | ✅ falha ⇒ `LoxRuntimeError` |
| `std.results` | `map`, `mapErr`, `unwrapOr`, `andThen`, `isOk`, `isErr`, `toOptional` | ✅ `Result[T, E]` |

**T2 — comum**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.json` | `parse`, `stringify`, `pretty` (ordem de inserção; `Int`/`Float` distintos) | ✅ |
| `std.fmt` | `format(template, List[Any])`, `pad`, `commas`, `fixed`, `percent`, `bytes` | ✅ |
| `std.paths` | `join`, `dirname`, `basename`, `ext`, `stem`, `normalize`, `isAbsolute`, `split` (POSIX) | ✅ |
| `std.fs` | `readText`, `readLines`, `writeText`, `appendText`, `exists`, `listDir` | ✅ ambiente (pytest); `fs.open`/streaming: ver §10 |
| `std.io` | `write`, `writeErr`, `readLine`, `readAll`, `prompt` | ✅ leitura ambiente (pytest) |
| `std.cli` | `parse(args, spec)`, `flag`, `option`, `positional`, `usage` | ✅ spec em `List[String]` |
| `std.sets` | `Set[T]` sobre `Map[Any, Bool]`: `add`, `has`, `remove`, `len`, `union`, `intersect`, `difference`, `toList`, `fromList` (classe em módulo) | ✅ (campo T em constraints pós-MVP) |
| `std.csv` | `parse`, `stringify` (RFC 4180, determinístico) | ✅ |
| `std.convert` | `toInt`, `toFloat`, `toBool`, `base64Encode`, `base64Decode`, `hexEncode`, `hexDecode` (texto UTF-8; sem tipo `Bytes`) | ✅ |

**T3 — extra**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.timex` | `iso`, `parseIso`, `daysFromCivil`, `civilFromDays`, `addDays`, `parts` (**UTC-only**) | ⬜ |
| `std.rand` | `seed`, `int`, `float`, `bool`, `shuffle` (PRNG em Lox, determinístico com semente) | ⬜ |
| `std.hash` | `fnv1a32`, `fnv1a64`, `djb2` (sobre `String`; não é cripto) | ⬜ |
| `std.collections` | `Stack`, `Queue`, `Deque`, `PriorityQueue` (classes em módulo) | ⬜ |
| `std.log` | níveis, `writeErr`, sem timestamp por padrão | ⬜ |
| `std.test` | `describe`, `it`, `expect`, `run` (mini-harness; usa `os.exit`) | ⬜ |

**Fora da stdlib:** a linha do topo da §13 (motivos no [ADR-0072](docs/adr/0072-stdlib-batteries.md)).

### 13.7 Ordem de entrega

| # | Passo | Esforço | Depende de |
| --- | --- | --- | --- |
| 0 | ✅ **GC Boehm + contrato de memória** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md), [ADR-0087](docs/adr/0087-heap-cap-e-self-hosting.md)): allocator, roots, hard cap default 512 MiB + `--max-heap`, I1 até 64 MiB live | M | — |
| 1 | ✅ **13.3** — cache de offsets + `substr`/`join`/`charCodeAt`/`fromCodePoint` + bench | M | 0 |
| 2 | ✅ **13.4** — tabela única de primitivas | S | 1 |
| 3 | ✅ **13.2** — kernel de SO: `args`, `io.*`, `os.*` + `main(argc, argv)` + exit code | M | 2 |
| 4 | ✅ **13.5** — imports/módulos + `std/strings` + `std/lists` mínimos | M | 3 |
| 5 | ✅ **T1** restante (`maps`, `numeric`, `asserts`, `results`) | M | 4 |
| 6 | ✅ **T2** (`json`, `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv`, `convert`) | M | 5 |
| 7 | **T3** + dogfooding: `lox fmt` em Lox, depois front-end self-hosted (§10) | L/XL | 6 |

Os passos 0–6 estão feitos: GC, kernel, tabela de primitivas, imports/módulos, T1 e T2
([ADR-0079](docs/adr/0079-stdlib-t2.md)). O próximo é o **limite de pilha**
([ADR-0077](docs/adr/0077-limite-de-pilha.md)). O `main` gerado agora é
`i32 main(argc, argv)`; o ABI das funções Lox não mudou.

### 13.8 Critério de pronto por módulo

- [ ] programa real em `exemplos/` ou caso que o use (não simetria com outra linguagem);
- [ ] golden em `tests/cases/std_<modulo>.lx` + `--check` limpo;
- [ ] determinismo declarado (função ambiente ≠ corpus I1);
- [ ] doc na spec quando o módulo estabilizar (e `sources:` válido);
- [ ] zero sintaxe nova — se precisar, é ADR-0066, não stdlib;
- [ ] `make check` verde; `make bench` se tocar caminho quente.

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
| 4 | {@14.4} Distribuição, stdlib instalada e pacotes | **pré-requisito técnico** do release da §14.1: hoje o wheel não entrega comando nem `std/` |
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
  e C (`runtime/runtime.c`); o código gerado não entra.
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
  *learn* e *reference*; ADRs não são traduzidos. Tradução congela texto, então cada página
  traduzida precisa do mesmo mecanismo de frescor, senão o inglês apodrece primeiro.
- **Playground:** o alvo é WASM (§6.10). Até lá, ou playground server-side (`run`/`--check`
  com timeout e sem rede), ou nenhum — não vale um serviço só para enfeite.
- **Gate:** `make docs-build` no CI (links quebrados, front matter inválido, página sem par
  traduzido). O `tests/test_docs_links.py` continua sendo o portão da fonte.

### 14.3 Servidor MCP (`loxia-mcp`)

Objetivo: um agente (Claude/Codex/DSH) escrever Loxia **que compila** e ler a spec sem
alucinar. O projeto está pronto de um jeito incomum: `--error-format=json` já devolve
envelope versionado (`schema_version`, `code`, `phase`, `span`) e o I3 garante os mesmos
bytes — diagnóstico determinístico é exatamente o que tool de agente precisa.

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

**O buraco, em fatos.** O repo funciona; o **pacote** não existe:

- `pyproject.toml` não tem `[build-system]` nem `[project.scripts]` — `pip install loxia`
  não produz o comando `loxia`;
- `std/` está fora do pacote Python e `STD_ROOT` resolve por
  `Path(__file__).parents[2] / "std"` (raiz do repo). Funciona no clone, **quebra no wheel**;
- a raiz de módulos é o diretório do arquivo de entrada; `..` e caminho absoluto são erro
  ([ADR-0073](docs/adr/0073-imports-modulos.md)). Consequência: um projeto **não consegue**
  consumir código fora da própria pasta — nem dependência, nem monorepo, nem a stdlib se ela
  não estiver no repo;
- `std.*` é raiz reservada e resolve no bundle; o loader **inlina** os módulos em
  compile-time, então tree-walk e backend usam a mesma resolução (bom: um caminho só).

**O que isso custa hoje.** Quem quiser experimentar precisa clonar, instalar `uv`, `libgc` e
`llvmlite`; e o primeiro usuário que tentar `import` de um pacote vai bater na regra do `..`.
É o maior *gap* entre "projeto impressionante" e "ferramenta" — e é o único que depende de
decisão de design, não de feature.

**Item 1 — empacotar e instalar (sem decidir resolução ainda).**

> Dívida do ADR-0088 **resolvida** em 2026-11-15: `src/` virou `loxia_core/`; o wheel
> não instala mais um pacote top-level chamado `src`.

- [x] `[build-system]` (hatchling) + `[project.scripts] loxia = "loxia.cli:main"`.
      Falta: `loxia run|check|build` como subcomandos (fase 0 da §14.7).
- [x] `std/` e `runtime/` viajam no wheel (`force-include` → `loxia_core/std`,
      `loxia_core/runtime`) e `loxia_core/bundle.py` resolve dev × instalado.
- [x] Teste de instalação real (`tests/test_install.py`, `pytest -m install`): builda o wheel,
      instala num venv fora do repo e roda `std.json`. Cobre também `--emit` com o runtime
      empacotado (verificado manualmente).
- [ ] `uv build` e sdist sem `std/` duplicado; `CHANGELOG`/README com o comando de instalação.

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

- [ ] **Fase 0 — CLI único** (junto da §14.4): `loxia run|check|build|fmt|test|repl|version`;
      as flags atuais continuam aceitas. Sem rede, sem config nova. É só o entry point e o
      despacho.
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
| `runtime/runtime.c` | ABI do backend; `driver.py` compila junto com o código gerado |
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
  principal, como `loxia lsp` (ou entry point `loxia-lsp`). O trabalho real do LSP é o
  modelo de diagnóstico do [ADR-0075](docs/adr/0075-diagnosticos-estruturados.md), que
  versiona junto com o compilador; separar criaria duas releases por mudança de span/código.
- O repo `loxia-editors` fica só com o **cliente** (extension manifest, grammar, packaging).
- Contrato: o servidor responde em processo, mas o mesmo resultado tem que sair de
  `loxia check --error-format=json` — teste de paridade, como no MCP.
- **Gatilhos para separar:** dependência própria (`pygls`/`lsprotocol`) que o runtime não
  deve ter, cadência de release dirigida por clientes de editor, ou um segundo mantenedor.
  Até lá, separar só paga o custo de sincronizar dois relógios.

**Não fazer:** abrir 6 repositórios antes do primeiro release (custo de CI/versão/
sincronização sem consumidor); mover `std/` ou `runtime.c` para fora (drift de ABI/versão);
duplicar a spec; separar o LSP para "ficar organizado" sem consumidor próprio.
