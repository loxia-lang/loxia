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

A fila ativa é curta: **M9**, **tooling de editor** e a trilha de publicação (§14); o M8
fechou com bench local e orçamento de monomorfização (ADR-0063).
LSP-2 e o lote de fixes estão fechados; dogfood/self-hosting ficam para depois do repo
público e documentado ([`IDEIAS.md`](IDEIAS.md)).
O status por nível é **gerado** em [`docs/spec/garantias.md`](docs/spec/garantias.md) a
partir de [`tests/corpus_manifest.py`](tests/corpus_manifest.py) — não copie números para cá.


### 0.2 Ordem de execução

1. [x] **M8** (`P2`): performance fechada — `-O2`, bench local e orçamento de
       monomorfização (ADR-0063); JIT no REPL é P3 e não bloqueia.
2. [ ] **M9** (`P2`): ecossistema — site, playground e publicação do cliente de editor
       (ADRs 0090–0093; §7 e §14).
3. [ ] **Publicação** (`P2`, paralela): §14 (repo privado pronto; falta 1.1.0, flip, site, MCP e distribuição).
4. [ ] **Depois do repo público:** dogfood/self-hosting do formatter e do front-end
       (§13.7, [`IDEIAS.md`](IDEIAS.md)).

> **Trilha paralela:** a §14 (publicação, distribuição, pacotes, corpus de conformidade e
> docs de usuário) não bloqueia nenhum nível da linguagem/backend e pode andar junto com a
> fila acima. Ela é pré-requisito de **adoção**, não de correção.


### 6.10 Bônus: WebAssembly

`llvmlite` sabe emitir para **wasm32** (`Target.from_triple("wasm32-unknown-unknown")`).
Isso permitiria um playground no navegador sem Pyodide — a linguagem rodando a 100% no
browser. Guardar como ideia P3 (precisa de runtime mínimo em wasm e de uma ABI de
imports para `print`).


---

## 7. Tooling e qualidade

- [ ] `P3` tree-sitter grammar (complemento do LSP; não substitui).
- [x] Fuzzing do scanner/parser com `hypothesis` (`tests/test_fuzz.py`, `make fuzz`).
- [ ] `P3` snapshot de AST em arquivo.
- [ ] `P3` site publicado a partir de `docs/` — ver §14.2 (stack, i18n e gate).
- [ ] `P3` servidor MCP (`loxia-mcp`) — ver §14.3; depende do CLI agent-friendly acima.

---

## 9. Milestones pendentes

M0–M7 estão fechados (ver [`docs/decisoes.md`](docs/decisoes.md)). Falta:

| # | Marco | Critério de pronto | Estado |
| --- | --- | --- | --- |
| **M8** | Performance | `-O2` e benchmarks feitos; orçamento de monomorfização implementado/medido (ADR-0063); JIT no REPL é P3 e não bloqueia | ✅ |
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

---

## 10. Parque de diversões (ideias soltas)

- [ ] **Compilar o próprio interpretador?**
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
2. **Stdlib pós-1.0:** T1/T2/T3 concluídas; `std.utf8` já cobre `byteLen` e coluna
   UTF-16. Restam apenas capacidades de host (`fs.open` em streaming, §13.9; `net`).
   `time` não determinístico e transcendentais de `math` continuam fora do I3.
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
9. **TOML na stdlib e `loxia add`:** implementar `add` com edição de manifest exige um
   writer de TOML; hoje o §13 lista YAML/TOML como fora. Decidir se TOML entra na stdlib
   (e com que escopo: parse + write canônico preservando comentários) antes de `add`;
   registry continua a fase 3 do §14.7.
---


## 13. Stdlib, kernel de primitivas e módulos

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


### 13.7 Dogfood e self-hosting — adiados
Portar `loxia fmt`/front-end para Lox e comparar byte a byte com o Python fica **depois**
do repo público e bem documentado; não é pré-requisito de M8/M9 nem da publicação do
cliente de editor ([ADR-0092](docs/adr/0092-estilo-e-formatter.md)).

### 13.9 Capacidades de host — `proc`/`poll` feitos; o resto não decidido

`io.flush`/
`readUtf8` e `proc`/`poll` estão implementados ([ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md),
[ADR-0095](docs/adr/0095-processos-streams-poll.md)); `fs.open`/`net` seguem não
aprovados, e o servidor LSP continua em Python.

`byteLen(s)` e a coluna UTF-16 (o LSP conta UTF-16, não code points) já estão em
`std/utf8` — são Lox puro e não precisam de kernel.

**Candidatas depois (cada uma pede ADR próprio):**

| Camada | Superfície | Consumidor | Esforço |
| --- | --- | --- | --- |
| `fs.open` | `open(path, mode) -> File` (streaming, §10) | arquivos grandes, CSV/log | M |
| `net` | `tcpListen`/`tcpConnect`/`accept`/`close` (+ unix) | só com consumidor (HTTP client, debugger remoto) | M |

**Ordem sugerida:** `fs.open` (M) → `net` (L, só com dor). O servidor LSP continua em Python
([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)) — não reabrir.

---

## 14. Publicação e ecossistema

### 14.0 Lacunas do produto (visão)

A linguagem e a stdlib T1–T3 estão fechadas; o que falta é a camada de produto. Esta
tabela é o resumo executivo; o detalhe fica nas subseções abaixo.

| Área | Estado | Gap de produto | Prioridade |
| --- | --- | --- | --- |
| **LSP residual** | diagnostics, hover, completion, codeAction, rename e workspace symbols | rename cross-file plenamente semântico, membros herdados na completion, signatureHelp de método importado e `inlayHint` | **P1** |
| **MCP** | contrato do CLI pronto (`--json`, `explain`, `capabilities`, `fix`) | servidor `loxia-mcp` ainda não existe | **P1** |
| **Robustez** | diferencial I1, determinismo, docs e fuzzing do front-end | snapshots de AST e LSP contra código incompleto | **P1** |
| **Debugger/playground** | — | DAP no tree-walk e playground WASM | P2/P3 |
| **Conformância** | corpus interno maduro | extrair `loxia-conformance` e runner genérico para outras implementações | P2 |
| **Performance** | bench local/baseline e orçamento de monomorfização medido (M8 ✅) | suíte pública de benchmarks só depois do release | P2 |
| **Tooling menor** | `fmt`, `test`, `fix`, `doc`, `explain`, `capabilities`, `lsp`, `repl`, `new`/`init` ([ADR-0106](docs/adr/0106-scaffolding-new-init.md)) | `loxia add`/`remove` (depois de stdlib de TOML) | P3 |



| # | Entrega | Por que nesta ordem |
| --- | --- | --- |
| 3 | {@14.3} Servidor MCP | depende da spec publicada e estável |
| 5 | {@14.5} Corpus de conformidade como artefato | em paralelo; depende do manifesto estabilizado (já está) |
| 6 | {@14.6} Primeiro programa real e docs de usuário | depende de 4 (instalar) e alimenta a §14.2 (tutorial/cookbook) |


### 14.1 Abrir o repositório

> **Status 2026-11-17:** o "contrato social", a licença dual, os templates, o Dependabot,
> o CI dividido e o README em inglês estão prontos no repo **privado**
> `loxia-lang/loxia`. O histórico foi reescrito para remover `IDEIAS-REDDIT.md`, a tag
> `v1.0.0` foi recriada e o repo antigo (`CassioDalla/my-lox`) foi arquivado. O bump
> 1.1.0 + CHANGELOG já estão prontos; falta a tag `v1.1.0`/push, o PyPI (pending publisher
> + 2FA) e o **flip para público** com os ajustes de segurança do GitHub.

- [ ] **PR 9 — release 1.1.0:** bump de versão, CHANGELOG 1.1.0 em inglês, tag `v1.1.0`,
  PyPI com pending publisher/2FA e badge PyPI no README. **Não fazer antes de fechar a
  revisão da Fase 1.**
- [ ] **Flip para público:** tornar `loxia-lang/loxia` público, habilitar CodeQL,
  private vulnerability reporting, secret scanning/push protection, branch/tag protection,
  topics e social preview.
- **Custo/risco:** público significa issue e PR de estranho; sem `CONTRIBUTING` a triagem
  vira ruído. E publicar **congela** API — por isso o
  [ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md) veio antes.

### 14.2 Documentação como site (+ i18n)

> **Status 2026-11-17:** desenho fechado no
> [ADR-0103](docs/adr/0103-site-de-documentacao-e-versionamento.md). A implementação vai do
> scaffold ao deploy em 7 PRs; o site é **build de `docs/`**, nunca fonte paralela.
> PRs 1–7 implementados em 2026-11-17; a referência normativa foi traduzida para inglês em
> `docs/spec/` no mesmo dia; o deploy fica condicionado ao flip público.

**Pendências do 14.2:** habilitar Pages no flip público (`docs.yml` está
condicionado a `repository.visibility == public`), trocar os rótulos 1.1 (next)/1.0
(stable) depois do PR 9 e ajustar os redirects de `/reference/*` e `/1.0/reference/*` se o
`base`/domínio mudar. O build do site já roda no CI.

**Riscos:** duplicação/idade do snapshot 1.0; manter a referência EN em passo com
`docs/spec/`; duas toolchains (Node + Python) e Dependabot npm; links absolutos quebrarem
no `base /loxia`; conteúdo do Learn envelhecer se os snippets não forem testados.

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


### 14.5 Corpus de conformidade como artefato

O que viaja não é a linguagem — é o **corpus**. Hoje ele já é maduro: casos `.lx`
autoexplicativos, manifesto por nível, promoção monotônica, runner diferencial nos três
canais.

> **Status 2026-11-17 — adiado por decisão.** O objetivo é contribuição ao ecossistema **e**
> vitrine, mas não há consumidor hoje e o artefato cria contrato público (versão, licença,
> issues, custo de mudar sintaxe depois). Retomar **depois do flip público + 1.1.0**
> (§14.1), começando pela camada **`lox-core`**; a camada `loxia` (dialeto) vem depois.
> Contrato de "passar": **stdout/exit exatos + categoria de erro** (`compile`/`runtime`),
> nunca texto de mensagem, com `skip`/`PENDING` por implementação. Semente do `lox-core`:
> suíte oficial do livro (MIT) + curadoria; o adaptador mecânico
> (`fun→fn`, `//→#`, `class B < A→class B(A)`, campos, `print expr;`) fica **no nosso
> repo**, fora do artefato. Gatilho para antecipar: um terceiro implementando Lox/Loxia ou
> pedido explícito da suíte.

- [ ] Extrair `conformance/` (ou repo próprio): casos anotados, manifesto, runner e README
      que explique o contrato (`# expect:`, `PENDING`, `NEGATIVE`).
- [ ] Fase 1 — **`lox-core`**: subconjunto compatível com o livro, para quem implementa
      jlox/clox; oráculo é o livro, não o nosso tree-walk (evita circularidade). Inclui
      casos que a Loxia falha de propósito (campos dinâmicos, ADR-0009).
- [ ] Fase 2 — **`loxia`**: o dialeto (`val`/`var`, `fn`, `print(...)`, enums, etc.) numa
      camada separada; sem essa separação o corpus só serve a nós.
- [ ] Runner genérico: `conformance run --impl "<comando>"` roda qualquer interpretador e
      compara stdout/exit + categoria de erro, sem depender do nosso CLI.
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
- [ ] **Gerador de release notes em Loxia** (dogfooding; ver
      [`IDEIAS.md`](IDEIAS.md) I-14): ler os commits desde a última tag, parsear
      Conventional Commits e emitir Markdown para o release; começar no CI/release, sem
      hook de commit.
- [ ] Tutorial de 30 min (base do `/learn` da §14.2) e cookbook a partir de `examples/`.
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

- [ ] **Fase 2.5 — `loxia add` (path/git)**: seria útil já sem registry (`add acme --path ../acme`
      e `add acme --git URL --rev X`, depois `lock`), mas editar `loxia.toml` preservando
      comentários/ordem exige writer de TOML. Fica para depois de uma stdlib de TOML (hoje
      YAML/TOML estão **fora** no §13); até lá o fluxo é editar à mão + `loxia lock`.
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
| `examples/`, `bench/` | rodam na suíte |

| Repo próprio | Quando | Dependência |
| --- | --- | --- |
| `loxia-editors` (VS Code + Shiki) | ao publicar no Marketplace | **cliente**: grammar gerada no principal + empacotamento da extensão; sem semântica |
| `loxia-lsp` | **não separar agora** — ver abaixo | consome `Checker`/`AST`/`SourceMap` direto; contrato de diagnóstico versiona junto |
| `loxia-mcp` | quando o MCP existir (§14.3) | CLI como caixa-preta, versão pinada |
| `loxia-conformance` | no primeiro release público | **espelho gerado** do corpus, nunca fonte de verdade |
| `loxia-site` | quando o site virar build próprio (§14.2) | consome `docs/` do principal |
| `loxia-playground` | com o alvo WASM (§6.10) | compilador como artefato |
| `loxia-bench` | só se a suíte virar pública | baseline acoplado à versão |

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
