# ADR-0003 — Diagnósticos por execução, sem estado global

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../IDEIAS.md`](../../IDEIAS.md) I-4, [ADR-0075](0075-diagnosticos-estruturados.md)

## Contexto

O `ErrorReporter` guardava `had_error`/`had_runtime_error` em atributos de **classe**. Um
erro de uma execução vazava para a próxima: no REPL, uma linha inválida fazia as seguintes
serem ignoradas; nos testes, a ordem importava. Também não dava para ter duas execuções
independentes no mesmo processo.

## Decisão

- `ErrorReporter` é uma **instância por execução**, criada em `Lox.run` e injetada no
  scanner, parser, resolver e interpretador.
- Cada `run`/`run_repl` começa com `reset()`.
- Sintaxe/escopo chamam `reporter.error(...)`; runtime lança `LoxRuntimeError` e o
  `interpret` captura e reporta.
- Exit codes: 65 compilação, 70 runtime, 66 arquivo.
- Mensagens em inglês, formato `[line N] Error at 'x': ...`.

## Consequências

### Positivas

- Zero vazamento de estado entre execuções/linhas do REPL/testes.
- Testes podem inspecionar `lox.reporter`, `scanner.reporter` e `parser.reporter`.
- Caminho aberto para múltiplas execuções concorrentes no futuro.

### Negativas / custos

- O reporter precisa ser passado adiante (construtor explícito); esquecer isso faz as flags
  divergirem.
- Ainda é um objeto mutável compartilhado dentro de uma execução (aceitável: uma thread por
  run).

### Neutras

- O formato de impressão continua acoplado ao reporter; a separação coleta × renderização
  fica para o redesign de diagnósticos (I-4).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Continuar global com `reset()` manual | o bug volta na primeira distração |
| Exceção por erro de compilação | impossibilita acumular vários erros |
| Reporter por fase | duplicaria estado e dificultaria agregar erros |

## Como verificar

- `tests/test_interpreter.py::test_errors_do_not_leak_between_runs`.
- `tests/test_error_reporter.py` (instâncias independentes).
- REPL: erro em uma linha, próxima linha executa normalmente.
