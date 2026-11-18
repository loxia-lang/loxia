---
name: lox-bench
description: Como medir performance com bench/run.py, ler o baseline e decidir quando atualizá-lo sem esconder regressão.
whenToUse: Antes/depois de mexer em caminho quente (scanner, parser, interpreter) ou ao investigar lentidão relatada.
---

# Benchmarks

## Comandos

```bash
make bench                                   # compara com bench/baseline.json
uv run python bench/run.py --repeat 7        # mais amostras, menos ruído
uv run python bench/run.py --json            # saída para script
make baseline                                # regrava o baseline (só quando for intencional)
```

## Modelo de medição

- Cada caso é um `.lx` executado como **processo** (`sys.executable main.py caso`),
  então o tempo inclui boot do Python (~40 ms). Por isso os casos devem durar
  **>100 ms**; se um caso novo ficar abaixo disso, aumente as constantes dele.
- Roda 1 vez de aquecimento + `repeat` medidas; o relatório usa a **mediana** e
  mostra o mínimo. Mediana > média em ambiente ruidoso.
- Regressão = mediana > `baseline * 1.35` (default). O exit code fica 1, então
  `make bench` serve de gate local.

## Baseline

- `bench/baseline.json` guarda a mediana por caso, com python/plataforma.
- **Não atualize para fazer o check passar.** Atualize apenas quando a mudança de
  performance for intencional — e explique no commit.
- Ao trocar de máquina/CI, compare com desconfiança: ruído de hardware > 35% é comum.
  Regere o baseline localmente e diga isso no PR.
- Baseline versionado é referência de tendência, não contrato absoluto.

## Adicionar um caso

1. `bench/cases/<nome>.lx`, determinístico, uma saída estável (`print` de um valor).
2. Precisa exercitar um caminho que ainda não é coberto. Casos atuais:
   `loop_sum` (laço+atribuição), `nested_loop` (blocos/escopos), `branchy`
   (if/else+lógica), `string_concat` (strings).
3. Meça isolado: `uv run python bench/run.py --repeat 5`, confira >100 ms.
4. `make baseline` e commite caso + baseline juntos.

## O que não concluir

- O tree-walk em Python não vai ficar "rápido"; o alvo é o backend LLVM (fila no `docs/roadmap.md`).
- Ganho de micro-otimização dentro de ±35% é indistinguível de ruído. Antes de
  otimizar, meça o mesmo caso 3 vezes em sequência.
- Não adicione `time`/`print` de instrumentação no interpretador para "medir":
  use o harness ou `--json`.
