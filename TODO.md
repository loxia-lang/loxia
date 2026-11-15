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
vale o que está aqui. Estado em 2026-11-15: **L0–L6, L7, M7 e T1 concluídos**; kernel v1,
tabela de primitivas, imports/módulos e a stdlib núcleo implementados. A próxima execução
é a **stdlib T2** (§13.6). O status por nível é **gerado** em
[`docs/spec/garantias.md`](docs/spec/garantias.md) a partir de
[`tests/corpus_manifest.py`](tests/corpus_manifest.py) — não copie números para cá.

### 0.1 Definições que não podem faltar antes de cada nível

| Antes de | O que precisa estar fechado | Estado |
| --- | --- | --- |
| **L6** | enums/`match`, exceções, `Any` e corpus completo | ✅ |
| **L7** | `mod.verify()`, `-O2`, benchmark nativo, erros de codegen | ✅ (JIT no REPL é P3 separado) |
| **M7** | GC Boehm + contrato de memória do [ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md) | ✅ implementado |
| **T1** | `std.strings`, `std.lists`, `std.maps`, `std.numeric`, `std.asserts`, `std.results` sobre módulos/imports | ✅ concluído |

### 0.2 Ordem de execução

1. [x] **T1 — stdlib núcleo**: `std.strings`, `std.lists`, `std.maps`, `std.numeric`,
       `std.asserts` e `std.results`; cada módulo com golden, `--check` e determinismo.
2. [ ] **T2 — stdlib comum**: `json`, `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv`,
       `convert`.
3. [ ] **Diagnósticos**: stack trace de runtime e fonte de módulo no checker.
4. [ ] **JIT no REPL** (`P3`): desenho próprio antes de codar; não bloqueia stdlib.
5. [ ] **M8/M9**: performance restante e ecossistema (formatter, LSP, playground).

## 3. Diagnósticos

O desenho e a primeira entrega estão no
[ADR-0075](docs/adr/0075-diagnosticos-estruturados.md): modelo `Diagnostic`,
códigos estáveis por família, spans (linha/coluna/offset), `human`/`short`/`json`,
ordenação/dedup/cap e caminho relativo determinístico. O catálogo em
[`docs/spec/erros.md`](docs/spec/erros.md) é **gerado** a partir de
`src/diagnostics/codes.py` (`make codes`).

### 3.1 O que ainda falta

- [ ] **Stack trace de runtime** (`P2`): frames `at f (linha N) ← main (linha M)`; no
      binário, decidir o custo de carregar frames.
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
lox run script.lox            # interpretador (hoje: main.py script.lox)
lox check script.lox          # só typecheck/resolver (hoje: --check)
uv run main.py --emit=ll  script.lox  # inspecionar LLVM IR (hoje)
uv run main.py --emit=obj script.lox  # .o para linkar (hoje)
uv run main.py --emit=exe -o app script.lox  # nativo (hoje)
lox build script.lox -o app   # nativo (quando o CLI ganhar subcomandos)
lox build script.lox --emit=ll        # equivalente futuro
lox jit script.lox            # MCJIT, sem arquivo intermediário
lox fmt script.lox            # formatador (dogfooding do parser)
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
- [ ] `P3` tree-sitter grammar + LSP mínimo (diagnostics/hover).
- [ ] `P3` `lox fmt` e teste de idempotência.
- [ ] `P3` site publicado (mkdocs/mdbook) a partir de `docs/`.

---

## 8. Lox2: o que ainda vale

| Recurso | Status | Nota |
| --- | --- | --- |
| iterador de usuário no `for-in` | ⏳ | o `for-in` embutido existe; falta protocolo |
| `print` como função (`println`) | ⏳ | depois da 1.0; statement é a decisão |
| variádicos `...args` | ⏳ | falta implementar |
| trailing closure | ⏳ | falta implementar |
| `type` alias | ⏳ | falta implementar |
| generics + constraints | ⏳ | funções T3b prontas; constraints pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| uniões + narrowing | 🟡 | `T?`/`is`/`while`/campos/índices prontos; falta merge CFG/aliasing |
| traits nominais + `implements` | ⏸ | decididos com métodos default; pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| operator overloading | ⏳ | depois de classes |
| namespaces/import | ✅ | [ADR-0073](docs/adr/0073-imports-modulos.md): arquivo=módulo, `_` privado, `std.*` e `from`/`as` |
| `try`/`raise` no backend | ✅ | tree-walk e backend L6 ([ADR-0042](docs/adr/0042-excecoes.md), [ADR-0062](docs/adr/0062-l6-excecoes-unwinding.md)) |
| `match` estrutural em uniões | ⏳ | enum/`match` exaustivo já existe ([ADR-0041](docs/adr/0041-enums-match.md)); falta união/estrutural |
| extension methods | ⏳ | depois do LLVM MVP e de traits |
| classes como valores / metaclasses | 🤔 | só se precisar |
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
nível afetado volta para a fila com caso diferencial. Traits nominais continuam pós-MVP e
não bloqueiam nenhum nível.

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

Nada aqui será feito por enquanto. Retomar só com dor demonstrada (um caso de uso real) ou
quando T6b/constraints existirem; o desenho está no
[ADR-0040](docs/adr/0040-generics-classes-desenho.md) §"Em aberto".

- [ ] `fn map[U]` — métodos genéricos: a função livre cobre; sem constraints o corpo só usa
      operações universais.
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
   adiados (§10). Constraints e traits nominais ficam pós-MVP
   ([ADR-0038](docs/adr/0038-traits-nominais.md)).
2. **Nome e extensão** definitivos (hoje "PyLox", `.lox`; nomes de trabalho na 1.0).
3. **Stdlib pós-1.0:** `io`, `string`, `collections`, `time` não determinístico;
   transcendentais de `math` fora do I3.
4. **Constraints de generics e traits genéricos:** falta desenhar `T: Trait`, coerência e o
   custo na monomorfização ([ADR-0038](docs/adr/0038-traits-nominais.md)).
5. **Contratos e agentes:** `requires`/`ensures`/`invariant`, `--contracts` default e JSON
   schema v1 com `fixes[]` — [`IDEIAS.md`](IDEIAS.md) I-4.
6. **`if`/bloco como expressão:** fora da 1.0; reavaliar quando houver dor real.
7. **Paralelismo (multithread):** em avaliação no [`IDEIAS.md`](IDEIAS.md); async é
   concorrência single-thread ([ADR-0037](docs/adr/0037-async-direcao.md)), não paralelismo.
8. **HIR-lite — gate explícito:** não construir agora. Trocar para HIR-lite só se um
   destes gatilhos disparar ([ADR-0065](docs/adr/0065-hir-lite-controle.md)):
   `lower_exceptions.py`/`lower_enums.py` passarem de ~350 linhas, o lowering precisar de
   mais de 2 níveis manuais de blocos/phi, ou uma feature exigir CFG explícito (stack
   trace com frames, cleanup dinâmico completo, JIT). `Any` e containers sozinhos não
   disparam.
9. **Cleanup de exceções:** `finally` cobre o corpus; cleanup dinâmico completo em
   `raise` através de frames aninhados é dívida declarada, não bloqueia a stdlib.
10. **Imports:** [ADR-0073](docs/adr/0073-imports-modulos.md) implementado; restam `..`
    fora da raiz e diagnóstico de checker com fonte do módulo.

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
| kernel | syscalls e representação | Python (oráculo) + C (binário) | `src/execution/primitives.py`, `runtime/runtime.c` |
| std | biblioteca | **uma** (Lox) | `std/*.lox` |
| módulos | nomeação e carga | loader/desugar, sem lógica | `src/loader/` |

**T0 — kernel v1 concluído** com 14 primitivas: `args`, `io.*`, `os.*`, `time.*`,
`substr`, `join`, `charCodeAt`, `fromCodePoint`. O teto de **15** do [ADR-0071](docs/adr/0071-primitivas-de-runtime.md)
existe para limitar a duplicação Python×C e a superfície de ABI; não é um número mágico.
`fs.listDir`, `fs.exists` e `os.cwd` entram só quando `std.fs`/`std.paths` precisarem e
passarem pelo ADR-0071 (entrar acima do teto exige remover outra ou justificar no ADR).

### 13.2–13.3 Kernel v1 e complexidade — concluídos

Kernel de SO (13.2) e cache de code points/`substr`/`join`/`charCodeAt`/`fromCodePoint`
(13.3) estão implementados e cobertos por `k0`, `tests/test_kernel.py` e
`bench/cases/string_scan.lox`. O detalhe fica no [ADR-0071](docs/adr/0071-primitivas-de-runtime.md);
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
| `std.lists` | `map`, `filter`, `each`, `fold`, `reduce`, `find`, `findIndex`, `any`, `all`, `none`, `count`, `sum`, `min`, `max`, `sort`, `reverse`, `slice`, `take`, `drop`, `zip`, `flatten`, `unique`, `contains`, `indexOf`, `first`, `last`, `getOr`, `chunk`, `partition`, `flatMap` | ✅ base + sort/gaps; `sortBy`/`groupBy` adiados ([ADR-0076](docs/adr/0076-std-lists-sort.md)) |
| `std.maps` | `entries`, `fromEntries`, `merge`, `pick`, `omit`, `mapValues`, `filterKeys`, `filterValues`, `invert`, `hasValue`, `getOr`, `toList` | ✅ `Map[String, V]`; `invert` é `Map[String, String]` (constraints de chave genérica pós-MVP) |
| `std.numeric` | `gcd`, `lcm`, `isPrime`, `primes`, `factorial`, `powMod`, `digitSum`, `isEven`, `isOdd`, `sign`, `mean`, `median`, `mode`, `variance`, `stddev`, `roundTo`, `toBase`, `fromBase` | ✅ estatísticas de `List[Int]`, vazio ⇒ `nil`; domínio inválido ⇒ `LoxRuntimeError` |
| `std.asserts` | `assert`, `assertEq`, `assertNotNil`, `fail` | ✅ falha ⇒ `LoxRuntimeError` |
| `std.results` | `map`, `mapErr`, `unwrapOr`, `andThen`, `isOk`, `isErr`, `toOptional` | ✅ `Result[T, E]` |

**T2 — comum**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.json` | `parse`, `stringify`, `pretty` (ordem de inserção; `Int`/`Float` distintos) | ⬜ |
| `std.fmt` | `format(template, List[Any])`, `pad`, `commas`, `fixed`, `percent`, `bytes` | ⬜ |
| `std.paths` | `join`, `dirname`, `basename`, `ext`, `stem`, `normalize`, `isAbsolute`, `split` (POSIX) | ⬜ |
| `std.fs` | `readText`, `readLines`, `writeText`, `appendText`, `exists`, `listDir` | ⬜ |
| `std.io` | `write`, `writeErr`, `readLine`, `readAll`, `prompt` | ⬜ |
| `std.cli` | `parse(args, spec)`, `flag`, `option`, `positional`, `usage` | ⬜ |
| `std.sets` | `Set[T]` sobre `Map[T, Bool]`: `add`, `has`, `remove`, `len`, `union`, `intersect`, `difference`, `toList`, `fromList` (precisa de **classe em módulo**) | ⬜ |
| `std.csv` | `parse`, `stringify` (RFC 4180, determinístico) | ⬜ |
| `std.convert` | `toInt`, `toFloat`, `toBool`, `base64Encode`, `base64Decode`, `hexEncode`, `hexDecode` (texto UTF-8 / `List[Int]` 0..255; sem tipo `Bytes`) | ⬜ |

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
| 0 | ✅ **GC Boehm + contrato de memória** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)): allocator, roots, hard cap 128 MiB, I1 até 64 MiB live | M | — |
| 1 | ✅ **13.3** — cache de offsets + `substr`/`join`/`charCodeAt`/`fromCodePoint` + bench | M | 0 |
| 2 | ✅ **13.4** — tabela única de primitivas | S | 1 |
| 3 | ✅ **13.2** — kernel de SO: `args`, `io.*`, `os.*` + `main(argc, argv)` + exit code | M | 2 |
| 4 | ✅ **13.5** — imports/módulos + `std/strings` + `std/lists` mínimos | M | 3 |
| 5 | ✅ **T1** restante (`maps`, `numeric`, `asserts`, `results`) | M | 4 |
| 6 | **T2** (`json`, `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv`, `convert`) | M | 5 |
| 7 | **T3** + dogfooding: `lox fmt` em Lox, depois front-end self-hosted (§10) | L/XL | 6 |

Os passos 0–5 estão feitos: GC, kernel, tabela de primitivas, imports/módulos e T1. O
próximo é **T2**, começando por `std.json` e `std.fmt`. O `main` gerado agora é
`i32 main(argc, argv)`; o ABI das funções Lox não mudou.

### 13.8 Critério de pronto por módulo

- [ ] programa real em `exemplos/` ou caso que o use (não simetria com outra linguagem);
- [ ] golden em `tests/cases/std_<modulo>.lox` + `--check` limpo;
- [ ] determinismo declarado (função ambiente ≠ corpus I1);
- [ ] doc na spec quando o módulo estabilizar (e `sources:` válido);
- [ ] zero sintaxe nova — se precisar, é ADR-0066, não stdlib;
- [ ] `make check` verde; `make bench` se tocar caminho quente.
