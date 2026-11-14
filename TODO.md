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
vale o que está aqui. Estado em 2026-11-14: backend em **L0–L6**; o L6 está completo, o
L7 começou pelo `mod.verify()` e o **M7 (GC Boehm)** foi implementado no
[ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md). A próxima execução é o
kernel v1 (§13.3), com o L7b em paralelo. O status por nível é **gerado** em
[`docs/spec/garantias.md`](docs/spec/garantias.md) a partir de
[`tests/corpus_manifest.py`](tests/corpus_manifest.py) — não copie números para cá.

### 0.1 Definições que não podem faltar antes de cada nível

| Antes de | O que precisa estar fechado | Estado |
| --- | --- | --- |
| **L6** | enums/`match`, exceções, `Any` residual, `repr` de enum e o que o ADR-0055 ainda lista | ✅ |
| **L7** | `mod.verify()` (feito), passes `-O2`, benchmarks, JIT e mensagens de erro de codegen | 🟡 |
| **M7** | GC Boehm + contrato de memória do [ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md) | ✅ implementado |

### 0.2 Ordem de execução

1. [x] **Fechar o L6 em três cortes** (ADRs 0061–0065, aceitos):
       - [x] **L6i — enums/`match`/`Result`**: ADR-0061 implementado; `LoxEnumValue`,
      construtores de variante, `match` com blocos/phi e `Any` tag ENUM.
- [x] **L6j — exceções/unwinding**: ADR-0062 implementado; `LoxTryFrame`/`LoxException`,
      `setjmp`/`longjmp`, `try`/`except`/`finally` e classes sintéticas de exceção.
- [x] **L6k — função genérica como valor**: ADR-0063; especialização no call site e
      cache, mantendo unboxed.
- [x] **L6 — completo**: todos os casos do corpus declarado compilam; `PENDING` zerado.
- [x] **L7a — `mod.verify()`**: verificação explícita do módulo LLVM antes de emitir,
      com `BackendError` (exit 65) e teste de IR inválido.
- [x] **M7 — GC Boehm**: alocador (`GC_malloc`/atômico), roots, hard cap de 128 MiB e I1
      até 64 MiB de memória viva ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md));
      vem antes do resto do kernel.
- [ ] **L7b — Qualidade restante**: passes `-O2`, benchmarks, JIT no REPL e mensagens de
      erro de codegen.
- [ ] **Kernel v1** (§13): 13.3 → 13.4 → 13.2, depois stdlib.

## 3. Diagnósticos

O desenho e a primeira entrega estão no
[ADR-0075](docs/adr/0075-diagnosticos-estruturados.md): modelo `Diagnostic`,
códigos estáveis por família, spans (linha/coluna/offset), `human`/`short`/`json`,
ordenação/dedup/cap e caminho relativo determinístico. Catálogo em
[`docs/spec/erros.md`](docs/spec/erros.md).

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
- [ ] **Catálogo de códigos gerado**: `docs/spec/erros.md` é escrito à mão; um comando
      `make codes` pode gerar a tabela a partir do `Code` (e o teste já exige cobertura).

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

**Teto proposto** ([ADR-0064](docs/adr/0064-orcamento-do-corpus.md)): `PENDING` ≤ 5% do
corpus (hoje 4/110 = 3,6%), sempre com nível/motivo, e `l?` proibido. O I1 só cobre
`LEVELS`; o teto impede que o teste verde vire ficção. Para features grandes, o caso
espera em issue/branch em vez de inflar `PENDING`.

```bash
uv sync --extra llvm
uv run pytest tests/test_backend.py -q
```

---

## 7. Tooling e qualidade

- [ ] `P2` testes diferenciais interpretador × LLVM no corpus **completo** (hoje: o corpus
      declarado em `LEVELS`).
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
| namespaces/import | ⏳ | fase A proposta em [ADR-0073](docs/adr/0073-imports-modulos.md) (só `std.*`); fase B (arquivos) em aberto; plano na §13 |
| `try`/`raise` no backend | 🟡 | tree-walk pronto ([ADR-0042](docs/adr/0042-excecoes.md)); unwinding no L6 |
| `match` estrutural em uniões | ⏳ | enum/`match` exaustivo já existe ([ADR-0041](docs/adr/0041-enums-match.md)); falta união/estrutural |
| extension methods | ⏳ | depois do LLVM MVP e de traits |
| classes como valores / metaclasses | 🤔 | só se precisar |
| FFI com C | ⏸ | **não haverá FFI genérica**: kernel fixo de primitivas ([ADR-0071](docs/adr/0071-primitivas-de-runtime.md)); reavaliar só com dor demonstrada |
| stdlib (`io`, `string`, `collections`) | 📝 | plano completo na §13 ([ADR-0072](docs/adr/0072-stdlib-batteries.md)); kernel mínimo primeiro, resto em Lox |
| `async`/`await` | ⏳ | direção no [ADR-0037](docs/adr/0037-async-direcao.md): colored, `Task[T]`, determinístico; só com I/O, pós-M7 |

Fora: VM própria, GC geracional, JIT tracing, cache de bytecode e `Object` raiz — o LLVM
cobre o codegen e o escopo humano manda.

---

## 9. Milestones pendentes

M0–M5 estão fechados (ver [`docs/decisoes.md`](docs/decisoes.md)). Falta:

| # | Marco | Critério de pronto | Estado |
| --- | --- | --- | --- |
| **M6** | LLVM vertical | L0–L6 completos e I1 verde no corpus anotado | ✅ |
| **M7** | Runtime completo | GC Boehm ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)) + I1 verde no corpus completo | 🟡 GC implementado; bench/corpus completo pendentes |
| **M8** | Performance | L7: `-O2`, benchmarks e JIT | ⬜ |
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

Achadas ao implementar o cabeçalho de runtime do [ADR-0075](docs/adr/0075-diagnosticos-estruturados.md).
Nenhuma está no corpus declarado; entram quando virarem caso diferencial.

- [ ] **`Any as T` não checa a tag no lowering**: `_unbox_any` extrai o payload direto, então
      `val x: Any = "a"; print x as Int` imprime lixo no binário (exit 0) em vez de panicar;
      o tree-walk levanta `R1011`. `tests/cases/any_casts.lox` só cobre casts válidos.
- [ ] **Exceção de usuário não capturada**: o binário imprime `MyError` sem a mensagem
      (`lox_throw` recebe `NULL` em `lower_exceptions.py`); o tree-walk imprime
      `MyError: falhou`. O corpus `exceptions.lox` só captura.
- [ ] **Classes de exceção sintéticas**: o tree-walk aceita `Exception("x")`/
      `LoxRuntimeError("x")` (aridade 1, campo `message`); o backend declara os construtores
      com aridade 0 e recusa a chamada com `R1005`.


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
- [ ] **Modo "strict"** vs "loose" para compatibilidade com Lox puro durante a transição.

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
8. **HIR tipada × extração:** a extração foi feita e o spike de `Any` não pediu HIR
   ([ADR-0049](docs/adr/0049-any-boxeado-spike-l6.md)); reavaliar depois de `Any`
   completo e containers estabilizados.
9. **Unwinding de exceções no backend:** `setjmp`/`longjmp` no runtime × retorno de erro
   explícito (`Result`-like) × tabelas de unwind do LLVM. Decidir antes de promover
   `exceptions`; mexe em ABI, no runtime C e no I1.
10. **Sintaxe de import:** [ADR-0073](docs/adr/0073-imports-modulos.md) propõe
    `import std.<módulo>` (namespace completo, módulos só de declaração, fase A só std).
    Aguarda aprovação humana no gate do ADR-0066; fase B (arquivos do usuário, caminho
    relativo, diagnóstico por fonte) fica em aberto.

---

## 12. Referências

- Livro: <https://craftinginterpreters.com/> — e a suíte de testes oficial em
  <https://github.com/munificent/craftinginterpreters/tree/master/test>.
- Lox2: <https://github.com/HallofFamer/Lox2> · docs <https://mysidia-inc.gitbook.io/lox2>
  (ler `notes/DESIGN.md` e `notes/TYPESYSTEM.md`).
- `llvmlite`: <https://llvmlite.readthedocs.io/> · <https://github.com/numba/llvmlite>
- LLVM LangRef: <https://llvm.org/docs/LangRef.html> · tutorial Kaleidoscope:
  <https://llvm.org/docs/tutorial/>
- *Mapping High-Level Constructs to LLVM IR*:
  <https://mapping-high-level-constructs-to-llvm-ir.readthedocs.io/> (closures, vtables, GC)
- Hindley–Milner (para o modelo mental de unificação):
  <https://en.wikipedia.org/wiki/Hindley%E2%80%93Milner_type_system>
- Crafting Interpreters, cap. 11 (resolver) e cap. 26 (GC) — reler quando chegar a vez.

---

## 13. Stdlib, kernel de primitivas e módulos

> **Escopo:** pós-1.0; **não** bloqueia L6/L7 (§0.2). O kernel v1 vem **depois do GC**
> ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)). Decisões:
> [ADR-0071](docs/adr/0071-primitivas-de-runtime.md) (primitivas e complexidade),
> [ADR-0072](docs/adr/0072-stdlib-batteries.md) (política de batteries) e
> [ADR-0073](docs/adr/0073-imports-modulos.md) (imports — **proposto**, aguarda o gate do
> ADR-0066).
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

### 13.2 Kernel v1 (teto: 15 primitivas)

| # | Primitiva | Assinatura | Amb.¹ | Estado |
| --- | --- | --- | --- | --- |
| 1 | `args` | `args() -> List[String]` | sim | ⬜ |
| 2 | `io.readFile` | `(path: String) -> String?` | sim | ⬜ |
| 3 | `io.write` | `(text: String)` — stdout sem `\n` | não | ⬜ |
| 4 | `io.writeErr` | `(text: String)` — stderr sem `\n` | não | ⬜ |
| 5 | `io.writeFile` | `(path: String, text: String) -> Bool` | sim | ⬜ |
| 6 | `io.readLine` | `() -> String?` (nil no EOF) | sim | ⬜ |
| 7 | `os.exit` | `(code: Int)` — não retorna; 0..255 | sim | ⬜ |
| 8 | `os.getenv` | `(name: String) -> String?` | sim | ⬜ |
| 9 | `time.now` | `() -> Int` (ms desde a época) | sim | ⬜ |
| 10 | `time.sleep` | `(ms: Int)` | sim | ⬜ |
| 11 | `substr` | `(s: String, start: Int, end: Int) -> String` | não | ⬜ |
| 12 | `join` | `(parts: List[String], sep: String) -> String` | não | ⬜ |
| 13 | `charCodeAt` | `(s: String, index: Int) -> Int` | não | ⬜ |
| 14 | `fromCodePoint` | `(codePoint: Int) -> String` | não | ⬜ |

¹ Ambiente = fora do corpus I1 (depende do SO/mundo). `io.write`/`io.writeErr` são
determinísticos e **podem** entrar no corpus. `args()` devolve os argumentos depois do
script/binário, para os dois motores verem a mesma lista.

**Fora do kernel v1** (candidatos à 15ª vaga): `fs.listDir`, `fs.exists`, `os.cwd`.
Entram só quando `std.fs`/`std.paths` precisar; cada um acima de 15 exige remover outro.

### 13.3 Complexidade (ADR-0071)

- [ ] `LoxStr` ganha `i32 *cp_offsets` (NULL até o primeiro acesso aleatório; só para
      `cp_len >= 64`), inicializado em **todo** construtor do runtime.
- [ ] `lox_str_char_at` O(1) usando o cache; `chars` e `for-in` sobre `String` O(n) total.
- [ ] `substr` O(1) para localizar + O(b−a) de cópia; `join` O(total).
- [ ] `charCodeAt`/`fromCodePoint` (Python + C + lowering + checker + spec).
- [ ] `bench/cases/string_scan.lox` (100k code points): antes **2,22 s**; alvo **≤ 0,05 s**.
      Registrar o número no commit e no ADR-0071.
- [ ] Reavaliar os testes de memória: o ponto do `Out of memory` muda com o cache e com o
      GC (ADR-0074); o hard cap é 128 MiB e o I1 cobre até 64 MiB live.
- [ ] `docs/spec/semantica.md` (+ nota "atualizado por ADR-0071" no ADR-0035, que é
      imutável).
- [ ] Nível `k0` no `tests/corpus_manifest.py` para os casos do kernel.

### 13.4 Tabela única de primitivas

- [ ] `src/execution/primitives.py`: `Primitive(lox, c_symbol, params, result, py, ambient)`
      + `PRIMITIVES`.
- [ ] Checker registra `FnTy` a partir da tabela (sem `if` por nome).
- [ ] Interpreter embrulha `py` num `LoxCallable` genérico (aridade/tipos da tabela).
- [ ] Backend resolve `c_symbol`/assinatura pela tabela (sem caso especial por nome).
- [ ] `tests/test_primitives.py` itera a tabela: um caso por primitiva, ordem e aridade.
- [ ] Opcional: migrar `len`/`chars`/`str`/`repr`/`range` (tipo sobrecarregado) — não
      bloqueia.

### 13.5 Imports — fase A (ADR-0073, proposto)

- [ ] **Aprovação humana** das quatro perguntas + dos quatro itens em aberto do ADR-0073.
- [ ] `TokenType.IMPORT` + `KEYWORDS` (25 → 26) + linha do ADR-0066 atualizada.
- [ ] Parser: bloco de imports só no topo (antes de qualquer outro statement).
- [ ] Loader: resolve `std.<modulo>` no bundle, dedup, ciclo diagnosticado.
- [ ] Desugar: mangle `std$strings$split` (separador não lexável) e reescreve
      `std.strings.split`; `std` reservado; módulo não é valor.
- [ ] Privacidade: `_nome` de módulo inacessível de fora.
- [ ] Reporter com **nome da fonte** (`std/strings.lox:12`), sem caminho absoluto (I3).
- [ ] Goldens (`tests/cases/imports/`): básico, dois módulos, genérico; negativos
      (import fora do topo, módulo inexistente, módulo como valor, `_privado`, ciclo,
      `std` redeclarado).
- [ ] `docs/spec/sintaxe.md` + `docs/spec/erros.md`; `--dump-ast` documentado como
      desugarizado.
- [ ] **Fase B** (arquivos do usuário): ADR próprio; restrições já decididas no ADR-0073 §5.

### 13.6 Batteries — inventário

Tiers do ADR-0072. `⬜` = a fazer; cada módulo entra com golden + `--check` + auditoria de
determinismo.

**T0 — kernel** (13.2): a base de tudo.

**T1 — núcleo**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.strings` | `split`, `splitLines`, `lines`, `words`, `trim`, `ltrim`, `rtrim`, `upper`, `lower` (ASCII), `capitalize`, `startsWith`, `endsWith`, `contains`, `indexOf`, `lastIndexOf`, `replaceAll`, `replaceFirst`, `repeat`, `padStart`, `padEnd`, `reverse`, `slice` (clamp), `isBlank`, `count` | ⬜ |
| `std.lists` | `map`, `filter`, `each`, `fold`, `reduce`, `find`, `findIndex`, `any`, `all`, `none`, `count`, `sum`, `min`, `max`, `sort`, `sortBy`, `reverse`, `slice`, `take`, `drop`, `zip`, `flatten`, `unique`, `contains`, `indexOf`, `first`, `last`, `getOr`, `chunk`, `partition`, `groupBy`, `flatMap` | ⬜ |
| `std.maps` | `entries`, `fromEntries`, `merge`, `pick`, `omit`, `mapValues`, `filterKeys`, `filterValues`, `invert`, `hasValue`, `getOr`, `toList` | ⬜ |
| `std.numeric` | `gcd`, `lcm`, `isPrime`, `primes`, `factorial`, `powMod`, `digitSum`, `isEven`, `isOdd`, `sign`, `mean`, `median`, `mode`, `variance`, `stddev`, `roundTo`, `toBase`, `fromBase` | ⬜ |
| `std.asserts` | `assert`, `assertEq`, `assertNotNil`, `fail` | ⬜ |
| `std.results` | `map`, `mapErr`, `unwrapOr`, `andThen`, `isOk`, `isErr`, `toOptional` | ⬜ |

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
| 1 | **13.3** — cache de offsets + `substr`/`join`/`charCodeAt`/`fromCodePoint` + bench | M | 0 |
| 2 | **13.4** — tabela única de primitivas | S | 1 |
| 3 | **13.2** — kernel de SO: `args`, `io.*`, `os.*` + `main(argc, argv)` + exit code | M | 2 |
| 4 | **13.5** — imports fase A + `std/strings` + `std/lists` | M | 3 |
| 5 | **T1** restante (`maps`, `numeric`, `asserts`, `results`) + `json`, `fmt` | M | 4 |
| 6 | **T2** restante (`paths`, `fs`, `io`, `cli`, `sets`, `csv`, `convert`) | M | 5 |
| 7 | **T3** + dogfooding: `lox fmt` em Lox, depois front-end self-hosted (§10) | L/XL | 6 |

O passo 0 está feito: o kernel e a stdlib em Lox agora têm heap coletado. O 13.4 pode
andar em paralelo ao 13.3; 13.3 e 13.2 tocam `LoxStr`/`main`/`runtime.c` e entram depois
dele. O passo 3 mexe no `main` gerado (`i32 main(void)` → `argc/argv`), mas não muda o
ABI de funções — os casos atuais do I1 continuam valendo; o programa que não usa `args()`
não muda de saída.

### 13.8 Critério de pronto por módulo

- [ ] programa real em `exemplos/` ou caso que o use (não simetria com outra linguagem);
- [ ] golden em `tests/cases/std/<modulo>/` + `--check` limpo;
- [ ] determinismo declarado (função ambiente ≠ corpus I1);
- [ ] doc na spec quando o módulo estabilizar (e `sources:` válido);
- [ ] zero sintaxe nova — se precisar, é ADR-0066, não stdlib;
- [ ] `make check` verde; `make bench` se tocar caminho quente.
