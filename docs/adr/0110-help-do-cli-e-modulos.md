# ADR-0110 — Ajuda do CLI por comando e divisão do `loxia/cli.py`

- **Status:** accepted (implemented)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (subcomandos e flags),
  [ADR-0075](0075-diagnosticos-estruturados.md) (diagnósticos),
  [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md) (pontos de entrada)
- **Implementação:** `loxia/cli.py` (dispatch), `loxia/cli_args.py` (superfície e validação),
  `loxia/cli_commands.py` (runners e `HANDLERS`) e `loxia/engine.py` (engine `Loxia`);
  testes em `tests/test_cli.py` e `tests/test_docs_consistency.py`.

## Contexto

O [ADR-0093](0093-cli-agent-friendly-e-reparo.md) manteve as flags antigas como aliases
aditivos, mas o `--help` do topo passou a listar o **modo compatível inteiro** —
`--dump-ast`, `--check`, `--emit`, `-o`, `--max-heap`, `--stdin`, `--timeout`, `--watch` —
como se fossem opções globais, quando cada uma pertence a um subcomando. Os comandos
apareciam só num epílogo em vírgula, e `loxia <comando> --help` mostrava
`description="loxia run"` (nada) com todas as opções num bloco único.

No código, `loxia/cli.py` tinha 1699 linhas e quatro responsabilidades (argparse, engine,
runners e dispatch), com duas árvores de opções/validação que já divergiam: `doc`
re-declarava `--error-format`/`--color`/`--max-errors` à mão, `fmt` validava por conta
própria e `Loxia.run_file` estava morto. Consumidores (fixer, rename, LSP) escreviam em
atributos privados da engine (`_file`, `_module_root`, `_sources`).

## Decisão

1. **O `--help` do topo é um índice**: comandos com uma linha de descrição, `-h`/`--version`
   em "opções globais" e, no epílogo, um resumo do modo compatível com as flags aceitas
   (gerado das ações do parser, sem lista paralela). Nenhuma flag de subcomando ocupa a
   lista de opções do topo.
2. **Cada `loxia <comando> --help` mostra só as flags daquele comando**, agrupadas
   (`entrada`, `saída do build`, `execução`, `diagnóstico`, `módulos e dependências`,
   `projeto`, `seleção`, `opções gerais`) e com exemplos no epílogo.
3. **O modo compatível continua parseável e validado** (`_validate_legacy`); só a
   apresentação muda. O README documenta os dois níveis.
4. **O CLI é dividido por responsabilidade**, com dependência em uma direção:
   `cli` → `cli_commands` → `engine`, e `cli_args` sem depender de execução. `HANDLERS`
   mapeia `COMMANDS` 1:1 (teste garante a paridade).
5. **A engine ganha API pública mínima** (`use_file`, `sources`, `flush`, `dependency_error`)
   e perde o método morto `run_file`; fixer/rename/LSP deixam de escrever em privados.

## Consequências

- O help responde "o que este comando faz?" sem despejar o legado; a descoberta dos
  comandos continua no topo e no README.
- Uma flag nova em um subcomando aparece no help do subcomando e no teste de cobertura do
  README, sem edição manual de uma terceira lista.
- **Custo:** quem dependia de ver as flags antigas na lista de opções do topo passa a
  vê-las no epílogo do modo compatível e no README.
- **Custo:** `capabilities` continua com a lista curada de features por comando (não é
  derivada do parser); a paridade `COMMANDS` × `HANDLERS` é testada, a de features não.
- **Custo:** quatro módulos exigem saber onde cada mudança mora; `HANDLERS` precisa entrar
  no mesmo commit de `COMMANDS` (o teste pega).
