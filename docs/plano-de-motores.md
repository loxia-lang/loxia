# Plano de motores — nativo primário, THIR e congelamento por módulo

Esta página é a **operação** do [ADR-0149](adr/0149-motores-primarios-thir-e-congelamento.md).
A divisão de responsabilidades é deliberada:

| Onde | O que guarda |
| --- | --- |
| ADR-0149 | a decisão, o porquê e o custo |
| **esta página** | fases, portões, indicadores e o painel |
| issues | o status (aberta/fechada, milestone) |

O `AGENTS.md` manda que issue é trabalho com critério de pronto e que o roadmap é
narrativa. Por isso: fases que vão acontecer nas próximas ~6 semanas viram issue agora; as
demais entram aqui e viram issue quando o portão anterior fechar. O painel desta página é
atualizado **no portão**, não a cada commit.

## Princípios

1. **Nativo é o produto.** `run` compila com cache; o tree-walk é REPL, `--interpret` e
   oráculo. Dev e prod usam o mesmo backend.
2. **Congela-se o motor, não o Python inteiro.** O checker é serviço de build e a última
   peça; enquanto ele for Python, "Python congelado" tem uma fronteira declarada.
3. **THIR é o eixo.** Uma árvore tipada e resolvida, sem desugaring de controle
   ([ADR-0156](adr/0156-sem-desugaring-no-thir.md)); não é CFG. O AST fica para tooling.
4. **IR de controle é interna ao backend.** Blocos/phi/cleanup; não é pública.
5. **Um interpretador.** THIR eval em Loxia; VM só com decisão explícita.
6. **O oráculo migra.** Python congelado → corpus dourado + spec; o diferencial vira
   THIR eval × compilador.
7. **Portão é técnico; data é consequência.** Nenhuma fase "fecha" por calendário.

## Ordem de congelamento

| # | Módulo Python | Substituto | Fica pinado por | Fase |
| --- | --- | --- | --- | --- |
| 1 | `execution/interpreter` + `semantics/resolver` | THIR eval em Loxia | REPL/oráculo | F3 |
| 2 | `backend/` (lowering + driver) | compilador Loxia | — | F4 |
| 3 | `frontend/` (+ `loader/`) | front Loxia | checker (até a ponte) | F5 |
| 4 | `semantics/checker` | checker Loxia | — | F6 |

O **runtime C nunca congela** (é o produto). O CLI/tooling pode ficar em Python
indefinidamente; portá-lo é projeto separado.

## Fases

As janelas são ilustrativas (meses a partir do início). O que decide é o portão.

| Fase | Janela | Entrega | Portão para avançar | Congela | Issue |
| --- | --- | --- | --- | --- | --- |
| **F0** | 0–1 | `run` AOT+cache; `--interpret`; medição | paridade de canais + latência aceitável + docs | — | [#244](https://github.com/loxia-lang/loxia/issues/244) |
| **F1** | 1–2 | IR de controle (blocos/phi/cleanup; [ADR-0153](adr/0153-ir-de-controle-desenho.md)) | ADR-0065 honrado; corpus verde; I4 | — | [#245](https://github.com/loxia-lang/loxia/issues/245) |
| **F2** | 2–5 | THIR + serialização; lowering consome THIR | **concluída em 2026-11-28**: 100% do corpus via THIR; side tables removidas; snapshot | — | [#270](https://github.com/loxia-lang/loxia/issues/270) |
| **F3** | 5–8 | THIR eval em Loxia (codename `loxvm`) | G1–G4 + soak 4 sem + fuzz 24 h | interpretador (+resolver) | [#284](https://github.com/loxia-lang/loxia/issues/284) |
| **F4** | 8–12 | compilador Loxia (THIR → `.ll` → `cc`) | G1–G4 + I4 + erros | lowering+driver | a abrir no fim de F3 |
| **F5** | 12–15 | front Loxia + ponte AST JSON | AST/JSON/diagnósticos 100% | frontend (+loader) | a abrir no fim de F4 |
| **F6** | 15–18+ | checker Loxia | paridade de `--check` + bootstrap | checker | a abrir no fim de F5 |

Dependências que não podem ser ignoradas:

- **F3 precisa do THIR serializado.** O `loxvm` não tem parser: ele consome THIR produzido
  pelo checker Python. É isso que permite congelar o interpretador **antes** do front.
- **F3 tem invocação decidida** ([ADR-0157](adr/0157-invocacao-e-distribuicao-do-thir-eval.md)):
  uma chamada só (`run --interpret`, THIR eval no G3; `--engine=thir|tree|native` na
  transição), payload em arquivo temporário e avaliador empacotado no wheel; a REPL fica no
  tree-walk congelado até a F5 e o G3 cobre execução one-shot.
- **F5 precisa da ponte AST JSON.** Sem ela, o checker Python não tem o que consumir e o
  front fica pinado; a fase não congela.
- **F4 e F3 podem andar em paralelo** (ambas consomem THIR), mas F4 depende de F3 ser um
  oráculo confiável.
- **F6 é o maior risco.** Se escorregar, o Nível 1 do self-host já está entregue e o Python
  só não foi totalmente aposentado.

## Medição F0 (2026-11-27)

`run` AOT com cache ([#244](https://github.com/loxia-lang/loxia/issues/244),
[ADR-0152](adr/0152-run-aot-aceitacao-flags-e-cache.md)), 8 núcleos físicos, cache limpo,
N=15 por cenário:

| Caso | `--interpret` P50/P95 | cold (runtime frio) | cold (runtime quente, `--no-cache`) P50/P95 | hit P50/P95 |
| --- | --- | --- | --- | --- |
| `examples/fizzbuzz.lx` | 94/97 ms | 1,27 s | 167/169 ms | 100/101 ms |
| `examples/fib.lx` | 96/97 ms | 1,27 s | 169/170 ms | 100/101 ms |
| `bench/cases/loop_sum.lx` | 581/589 ms | 1,26 s | 164/166 ms | 100/101 ms |

O hit paga ~5 ms sobre o interpretado em programa minúsculo (parse + chave + exec) e ganha
~5,8× no `loop_sum`. A primeira execução da máquina paga ~1,1 s das unidades de runtime
(cache por conteúdo, uma vez por versão/toolchain) — acima do gatilho de 1 s do ADR-0149;
registrado como candidato a aquecer o runtime no primeiro `build`/install, não resolvido na
F0. `make bench` continua medindo o interpretador (`--interpret`); `bench/run.py --native`
mede o binário.

## Portões

Um módulo congela quando **todos** valem. O portão é verificável; a data não.

| Portão | Critério | Como medir |
| --- | --- | --- |
| **G1 Paridade** | 100% dos casos do módulo (positivos + `NEGATIVE` + `COMPILE_ERRORS`) batem byte a byte | `tests/corpus_manifest.py` + golden |
| **G2 Soak** | 4 semanas / N execuções sem divergência; fuzz de 24 h sem diff | contador de divergências + campanha de fuzz |
| **G3 Default** | o substituto é o caminho padrão; o antigo só roda no corpus congelado | flag/engine padrão |
| **G4 Docs** | `spec/garantias.md` + ADR + CHANGELOG registram o congelamento e a cobertura ("linguagem ≤ versão N") | diff de docs revisado |
| **G5 Remoção** | após 2 releases sem rollback, mover para `oracle/` (read-only) ou remover | release notes |

"Congelado" significa **não recebe feature nova**; só bugfix de regressão do núcleo antigo.
O módulo continua rodando o corpus congelado como rede de regressão.

## Indicadores

Não use LOC como progresso. Use:

| Indicador | O que mede | Meta no portão |
| --- | --- | --- |
| `parity_<módulo>` | casos que batem / total | 100% |
| `open_divergences` | divergências abertas | 0, tendência zero |
| `soak_days` | dias desde a última divergência | ≥ 28 |
| `fuzz_hours` | horas de diferencial aleatório sem diff | ≥ 24 |
| `default_engine` | qual motor `run`/`build` usa | substituto = verdadeiro |
| `python_imports_from_<módulo>` | acoplamento residual | 0 (teste de camadas) |
| `pending` | lacunas declaradas no corpus | ≤ 5% (ADR-0064) |
| `run_latency_p50/p95` | cold/warm do `run` | registrado; cold < 1 s em programa pequeno |
| `golden_coverage` | casos com golden versionado | 100% no portão |

### Painel (scorecard)

Atualize a cada portão; um exemplo no fim de F3:

| Módulo | Substituto | Paridade | Soak | Default | Status |
| --- | --- | --- | --- | --- | --- |
| interpretador | THIR eval (Loxia) | 264/264 | 31 d | sim | 🟢 congelado |
| lowering | compilador Loxia | 240/264 | 9 d | sim | 🟡 em soak |
| front | front Loxia | 310/338 | 2 d | não | 🔴 em paridade |
| checker | checker Loxia | 120/240 | 0 | não | ⚪ não iniciado |

O painel é **manual e datado**; o status real está nas issues. Se o painel e a issue
divergirem, a issue vence.

## O corpus como oráculo

Enquanto o Python não congela, ele é normativo (I1 de hoje). No portão F3:

- cada caso ganha um **golden** com stdout/stderr/exit em bytes;
- o golden do núcleo ≤ N é gerado pelo **Python congelado** (independente);
- o golden de feature nova é **escrito a partir da spec**, nunca gerado pelo motor sob teste;
- atualizar golden é revisão consciente, como o snapshot do [ADR-0129](adr/0129-oraculo-do-front-end.md);
  "consertar para passar" é proibido;
- o diferencial continua como segunda checagem de codegen (THIR eval × compilador).

O `.lx` continua com `# expect:` para humanos; o golden é a camada de máquina. O formato
exato (diretório, JSON por caso, hash de versão) é decidido na F2/F3, mas o princípio acima
não muda.

## Self-host em níveis

| Nível | Definição | Meta |
| --- | --- | --- |
| **1 — self-executing** | front + interpretador + compilador em Loxia; checker Python como serviço de build; Python só no bootstrap | ano 1 |
| **2 — self-hosted** | checker em Loxia; o toolchain se constrói sozinho | ano 2 |
| **3 — reprodutível** | stage0 → stage1 → stage2; stage1 ≡ stage2 | depois de 2 |

"Self-executing" já é uma vitória de credibilidade: o binário roda e compila Loxia sem
Python. "Self-hosted" é o objetivo pessoal; o checker é a conta.

## Riscos e mitigação

| Risco | Sinal | Mitigação |
| --- | --- | --- |
| Port do checker escorrega | F6 sem paridade | Nível 1 entregue; checker Python como build service; issue separada |
| Front pinado pelo checker | F5 não congela | ponte AST JSON antes de F5; round-trip testado |
| THIR vira CFG | nós de fluxo/phi no THIR | THIR é árvore; controle desce para a IR do backend |
| Tentação da VM | "o REPL precisa ser rápido" | decisão explícita; um interpretador; medir antes |
| Golden drift | expectation muda "para passar" | golden do núcleo gerado pelo Python congelado; diff revisado |
| Cache do `run` erra | binário velho/stale | chave cobre fonte+deps+compilador+flags+plataforma+heap; teste de invalidação |
| Bootstrap quebrado | stage1 ≠ stage2 | stage0/stage1 reprodutível; comparar comportamento antes de bits |

## Ritual de atualização

1. Ao fechar um portão: atualizar o painel, registrar a data, congelar a cobertura no
   `spec/garantias.md` e no CHANGELOG.
2. Abrir a issue da fase seguinte (regra das ~6 semanas do roadmap).
3. Se um risco mudar de ordem, atualizar a tabela de riscos **antes** de mudar o código.
4. Este documento é versionado; mudou a estratégia, muda aqui e no ADR (novo ADR se a
   decisão mudar, não edição do aceito).

## Issues macro

| Fase | Issue | Estado |
| --- | --- | --- |
| F0 | [#244](https://github.com/loxia-lang/loxia/issues/244) `tooling: run compila com cache (AOT) e --interpret` | entregue (2026-11-27) |
| F1 | [#245](https://github.com/loxia-lang/loxia/issues/245) `backend: IR de controle (blocos, phi, cleanup)` | entregue (2026-11-27, [#275](https://github.com/loxia-lang/loxia/pull/275)) |
| F2 | [#270](https://github.com/loxia-lang/loxia/issues/270) `backend: THIR + serialization` | **concluída** (2026-11-28) |
| F3 | [#284](https://github.com/loxia-lang/loxia/issues/284) `loxvm: THIR eval in Loxia` | aberta |
| F4–F6 | — | a abrir no fim da fase anterior |

## Referências

- [ADR-0149](adr/0149-motores-primarios-thir-e-congelamento.md) — a decisão.
- [ADR-0002](adr/0002-tree-walk-como-oraculo.md) — o tree-walk como oráculo.
- [ADR-0065](adr/0065-hir-lite-controle.md) — o gatilho da IR de controle.
- [ADR-0129](adr/0129-oraculo-do-front-end.md) — o snapshot do front.
- [`docs/spec/garantias.md`](spec/garantias.md) — I1–I4.
- [`tests/corpus_manifest.py`](../tests/corpus_manifest.py) — o corpus e os níveis.
