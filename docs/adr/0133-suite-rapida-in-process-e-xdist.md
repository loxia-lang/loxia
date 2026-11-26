# ADR-0133 — Suíte rápida: CLI in-process e xdist no loop local

- **Status:** accepted (implemented)
- **Data:** 2026-11-22
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0096](0096-testes-biblioteca-e-runner.md) (runner `loxia test` e
  isolamento por processo), [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4),
  [`../tech/test-report.md`](../tech/test-report.md), [`../roadmap.md`](../roadmap.md)
- **Implementação:** `tests/inprocess.py`, `tests/runner.py`, `tests/test_official_suite.py`,
  `tests/test_toml_parity.py`, `tests/test_std_t2.py`, `tests/test_official_check.py`,
  `tests/test_docs_snippets.py`, `tests/test_examples.py`, `tests/test_fix.py`,
  `tests/test_test_runner.py`, `Makefile` (`test-fast`, `TEST_JOBS`),
  `tests/test_runner.py` (paridade fast × subprocesso)

## Contexto

`make check-fast` levava ~149 s para ~1.8 mil testes sem backend. O custo não estava na
linguagem: cada caso golden (303), cada caso da suíte oficial (120) e cada rodada do TOML
(36) abria um processo Python novo. Só o boot + import do CLI custa ~0,10–0,15 s; multiplicado
por ~500 execuções, isso era a maior parte da suíte. O boot não testa nada: o contrato que
importa é stdout, stderr e exit code.

O runner também é usado como ferramenta (`python -m tests.runner`) e a suíte oficial/TOML
depende de `--check`, argumentos de script e módulos. Qualquer solução precisava preservar
esse contrato observável e continuar cobrindo o processo de verdade onde ele é o objeto do
teste (hash seed, sinais, stdin de REPL, sandbox, backend nativo).

## Decisão

### 1. CLI in-process por padrão nos testes de caso

`tests/inprocess.py::run_cli` chama `loxia.cli.main()` no processo do pytest, com
`sys.argv`, `stdin`, `cwd` e `os.environ` controlados e restaurados, capturando stdout,
stderr e `SystemExit` (o mesmo par `returncode`/`stdout`/`stderr` de
`subprocess.CompletedProcess`). Golden, suíte oficial, paridade TOML, `--check` da stdlib,
snippets de docs, exemplos, `loxia fix` e a chamada externa de `loxia test` usam esse
caminho.

`tests/runner.py` mantém `LOX_GOLDEN_SUBPROCESS=1` como escape hatch: ele força um processo
por caso e existe para depurar uma diferença que só apareça com isolamento real.

### 2. Processo de verdade continua em subprocesso

Continuam com `subprocess` os testes cujo objeto é o processo: `tests/test_determinism.py`
(`PYTHONHASHSEED`, `cwd`, `--emit=ll`), timeout/sinais, REPL com stdin real, sandbox,
MCP/LSP sobre stdio, backend nativo e o `loxia test --isolate` (que precisa matar
subprocessos sem derrubar a suíte).

### 3. O loop local paraleliza; o gate não muda

`make test-fast` roda `pytest -m "not backend and not install" -n $(TEST_JOBS)` com
`TEST_JOBS ?= auto`. `TEST_JOBS=0` desliga o xdist para depurar um caso. `make test`,
`make check` e o CI continuam seriais e com a mesma seleção de antes; o teste de wheel
(`install`) deixa de entrar no loop rápido, que antes o puxava por causa do `-m` da linha
de comando sobrescrever o `addopts`.

## Consequências

### Positivas

- ~1.8 mil testes não-backend em **~15–20 s** com xdist nesta máquina (149 s antes; ~83 s
  em modo serial só com o caminho in-process).
- O contrato observável não muda: o caminho rápido foi comparado byte a byte com o
  subprocesso nos 303 casos golden; um teste de paridade cobre sucesso, erro de runtime e
  erro de compilação.
- Menos processos deixa o loop local mais estável sob carga e reduz o custo de rodar a
  suíte em máquinas pequenas (o pior caso é o modo serial, ainda ~45% mais rápido).

### Negativas / custos

- Estado de módulo passa a ser compartilhado entre casos no mesmo worker. A engine é
  desenhada sem estado global por execução (ADR-0003), mas um teste novo que mute um global
  (cache, `os.environ`, `cwd`) pode vazar para o próximo; o harness restaura argv, stdin,
  cwd e env, não caches arbitrários.
- Um crash duro (segfault) no caminho in-process derruba o worker do xdist; módulos nativos
  que podem falhar assim (regex Rust) continuam cobertos pelo backend e por testes com
  subprocesso.
- `-n auto` usa uma CPU por worker; em máquina já carregada o ganho cai e pode valer
  `TEST_JOBS=0`.
- O caminho rápido não exercita `main.py` como arquivo: um erro no bootstrap do entrypoint
  só aparece nos testes de CLI/processo.

### Neutras

- `make check-fast` continua sendo a soma de lint, format, mypy, pytest e freshness; o
  ganho é todo no pytest.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter um processo por caso | É o custo dominante; nenhum contrato ganha com o boot. |
| `os.fork()` por caso | Preserva isolamento, mas não é portátil (Windows) e complica captura de saída/exit code. |
| Só xdist, sem in-process | Ajuda, mas mantém ~500 boots e deixa pouca margem para 30 s em máquinas menores. |
| xdist no `make test`/CI | Backend compila e cacheia binários; paralelizar por padrão muda o perfil de falha e o gate. O CI já usa xdist só onde precisa (coverage). |
| Rodar cada caso via uma API de engine (sem `main`) | Perderia argparse, exit codes e o caminho real do CLI; `main()` é o contrato que queremos manter. |

## Como verificar

```bash
make test-fast                 # ~15-20 s, ~1.8 mil testes
make test-fast TEST_JOBS=0     # serial, para comparar
make test-backend              # backend sem os slow; ~12 s (crate intocado; cache vazio ~13 s)
make test-backend-all          # backend completo (inclui o crate Rust)
make test-backend TEST_JOBS=0  # backend serial, para comparar
uv run pytest -m smoke -q      # um caso por nível, em processo real
LOX_GOLDEN_SUBPROCESS=1 uv run pytest tests/test_golden.py -q
uv run pytest tests/test_runner.py -q   # paridade fast × subprocesso
```

Critério para revisitar: se o modo in-process começar a divergir do subprocesso (paridade
quebrada ou vazamento de estado entre casos), voltar o runner para subprocesso e manter só
o xdist; se um caso novo exigir processo real, marcar o teste e usar `subprocess`.

## Emendas

- **2026-11-26 — loop local do backend.** A decisão 3 continua valendo (`make test`,
  `make check` e o CI seguem seriais), mas o mesmo recorte do `test-fast` ganhou uma porta
  explícita: `make test-backend` roda `pytest -m backend -n $(TEST_JOBS)`
  (`TEST_JOBS ?= auto`; `0` desliga). Cada caso do corpus já é um subprocesso com `tmp_path`
  próprio e o cache do runtime é atômico; o CI já roda `-m backend` com xdist no job de
  cobertura (`coverage-*`, `COVERAGE_JOBS`), então nada de contrato mudou. Medição nesta
  máquina (16 cores, caches quentes, 472 testes): **172 s serial → 41 s com `-n auto`**
  (~4,2×); `-n 8` dá 44 s — acima de 8 workers o ganho achata (link + I/O). O que a emenda
  **não** resolve é o custo fixo por caso (~0,3 s, dominado por dois boots do Python e
  imports) e a recompilação de todo caso a cada run; o follow-up ficou em #230 (corpus
  in-process), #231 (cache de binário por conteúdo) e #232 (casos lentos + smoke local).

- **2026-11-26 — corpus diferencial in-process (issue #230).** O oráculo e o build dos
  casos diferenciais (`test_manifesto`, `test_binario_concorda_com_interpretador`, os
  goldens de erro de runtime) rodam no processo do pytest via
  `tests/inprocess.py::run_cli`; o binário compilado continua sendo executado em
  subprocesso. Medição nesta máquina (8 núcleos físicos / 16 threads, seleção
  `-m backend`): **43,5 s → 31 s com os caches de build frios e 11,1 s com o cache quente**
  — o `run_cli` por caso custa ~60 ms de build em vez de ~0,3 s de CPU. Os goldens de erro
  de runtime deixaram de ser um laço único (piso serial de ~30 s) e viraram casos
  parametrizados, que o xdist distribui; só os que passam no `--check` entram, e o filtro
  roda na coleta (um `skip` dentro do teste esconderia a perda total de cobertura).

  O aceite do issue (`< 10 s` em 16 núcleos) **não foi cumprido nem medido no hardware-alvo**:
  esta máquina tem 8 núcleos físicos e o backend quente fica em ~11-12 s; o resultado
  verificável aqui é a queda de 43,5 s para ~12 s.

  A rede de segurança é dupla: `test_smoke_do_backend_em_processo_real` roda **um caso
  por nível** (`-m smoke`) pelo caminho de processo real (e não arrasta o crate Rust) e
  `test_caminho_in_process_bate_com_subprocesso` compara stdout, stderr e exit code
  entre `run_cli` e o processo real, no oráculo e no build.

  Continuam em subprocesso os testes cujo objeto é o processo (`std.proc`, stdin real,
  sandbox, sinais, GC/pilha/oom, `--emit=ll`) e o **oráculo dos programas que usam o
  motor nativo de regex**: o binding `ctypes` é global ao processo, então handles de um
  programa sobreviveriam ao seguinte (`groupNames(1)` deixaria de ser "unknown") — o
  primeiro vazamento encontrado por este trabalho. Um crash duro no lowering ainda
  derruba o worker do xdist (antes derrubava um teste) e não há timeout por caso além do
  `timeout = 180` do pytest; o oráculo segue vivo a cada run, nunca um snapshot (I1).

- **2026-11-26 — casos lentos fora do loop e smoke local (issue #232).** `make test-backend`
  passa a selecionar `-m "backend and not slow"`. O marcador cobre os 3 casos do manifesto
  com `# requires: rust`, os 5 `test_regex_*` e o golden `std_regex/limits`: 9 dos 533 itens
  da seleção `-m backend`. `make test-backend-all` roda tudo; `make test`/`make check`, o
  alvo de cobertura do CI (`LOX_REQUIRE_LLVM=1`) e o `-all` não filtram nada. Medição nesta
  máquina (8 núcleos físicos): o loop fica em **11,6 s com o cache de build quente e 13,3 s
  com ele vazio** (antes: 11,1 s quente e 31 s frio); o delta do cache vazio vem das
  unidades C do runtime, porque o crate Rust deixa de ser tocado no loop. O `-all` mede
  29,2 s com os caches frios.

  `make check-fast` ganhou `make smoke-backend`: um caso por nível pelo caminho de processo
  real (~5 s, sem o crate Rust), com skip limpo por teste quando faltam `llvmlite`, `cc` ou
  `libgc` (o skip de módulo fazia `pytest -m smoke` sair 5 e quebrava o loop; os módulos de
  teste que importam o driver no topo ganharam `importorskip`). Guardas:
  `test_loop_local_exclui_slow_e_gate_inclui` (todas as receitas que rodam o backend,
  inclusive `coverage-backend`, `test-backend-all` e as dependências de `check`),
  `test_casos_rust_do_manifesto_sao_slow`, `test_testes_de_regex_sao_slow` e
  `test_casos_que_usam_o_motor_de_regex_declaram_rust` — um caso Rust novo sem `slow`/sem
  a diretiva, ou um gate que filtre `slow`, falham a suíte.

  Fora do escopo: a suíte golden (`tests/test_golden.py`, `test-fast`) continua rodando
  `std_regex/**` no processo — num cache frio o primeiro caso paga o build da lib nativa
  (~13 s) e os handles `ctypes` são compartilhados entre casos. Os dois efeitos estão
  registrados na #239.

  A fixture de sessão para aquecer `native_build` (proposta no issue) ficou de fora: o
  custo é o build do crate, não o primeiro teste — aquecer só move os ~20 s para o começo
  e, com xdist, todos os workers esperam o mesmo build (medido: `library()` 12,5 s +
  `static_library()` 7,9 s a frio). O marcador resolve o loop sem essa coreografia.

## Referências

- [ADR-0096](0096-testes-biblioteca-e-runner.md) — `loxia test`, isolamento por arquivo/teste.
- [ADR-0003](0003-diagnosticos-por-execucao.md) — diagnóstico por execução, sem estado global.
- [`../../tests/AGENTS.md`](../../tests/AGENTS.md) — regras locais da suíte.
- [`../tech/test-report.md`](../tech/test-report.md) — contrato do `loxia test --json`.
