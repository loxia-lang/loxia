# Changelog

Todas as mudanças relevantes da linguagem/interpretador. Decisões fechadas em
[`docs/decisoes.md`](docs/decisoes.md).

## [Unreleased]

### Mudado (quebra)

- **`std.timex` em milissegundos** ([ADR-0122](docs/adr/0122-contrato-de-data-e-instante.md),
  [#78](https://github.com/loxia-lang/loxia/issues/78)): `iso`, `parts`, `parseIso` e `addDays`
  passam a receber/devolver ms, a mesma unidade de `time.now()`. A migração é `x * 1000`; não
  há aliases em segundos. A formatação continua truncando para o segundo (`iso`) ou expondo
  `.mmm` (`isoMillis`).

### Adicionado

- **`Bytes` (fase 79a)** ([ADR-0125](docs/adr/0125-bytes-tipo-binario.md),
  [#79](https://github.com/loxia-lang/loxia/issues/79)): tipo de valor imutável para dados
  binários, distinto de `String`; `len` em bytes, `b[i] -> Int`, igualdade estrutural,
  `str`/`repr` em `0x<hex>`, `is`/`as`, `Any`, `List` e `Bytes?`. Namespace `Bytes`
  (`empty`, `fromList`, `fromText`, `fromHex`, `fromBase64`) e métodos (`slice`, `concat`,
  `toList`, `toText`, `toHex`, `toBase64`), com `BytesError` global
  (`InvalidHex`/`InvalidBase64`/`InvalidUtf8`). Hex aceita ambas as
  caixas; base64 é canônico; `toText` é UTF-8 estrito. Backend com tag 13
  (`runtime/bytes.c`), boxe em `Any`/`List`, `Bytes?`, `is`/`as` e `for byte in b`
  produzindo `Int`. Referência de método permanece lacuna declarada no backend (PENDING).

- **`Bytes` (fase 79c)**: `std.bytes` (`Builder` incremental sobre `List[Int]`,
  `ChunkBuilder` para blocos, `compare` lexicográfico, encoders `u16be/le`, `u32be/le`,
  `u64be/le` e decoders `readU16/32/64be/le` com `Int?`), `fs.readBytes`/`File.readBytes`
  (binário cru, grupo `fs` 11) e `digest.sha256Bytes`/`std.hash.sha256Bytes` (32 bytes
  crus, grupo `digest` 2). O kernel fecha em **40** primitivas.

- **`std.timex` v2**: `date` com validação (`Result[(Int, Int, Int), TimeError]`),
  `isLeapYear`, `daysInMonth`, `weekday` (ISO 1..7), `dayOfYear`, `addMonths`/`addYears` com
  clamp de calendário, `diffDays` (dias civis), `isoMillis`, `isoDate`, `isoIn`/`partsIn`
  (offset explícito `-720..840`) e parse de `YYYY-MM-DD`, fração de 1–3 dígitos, offset
  `±HH:MM` e `t`/`z` minúsculos (RFC 3339). `TimeError.kind` ganha `invalidDate`.

### Corrigido

- **`Bytes` é truthy no backend**: `if (b)`, `not b` e `and`/`or` sobre `Bytes` deixam de
  falhar no lowering; só `nil`/`false` são falsy, como no tree-walk.
- **Namespace nativo sombreado**: `val Bytes = ...`, `val fs = ...`, `val Int = ...` e
  equivalentes locais não são mais despachados como namespace global no backend.
- **Localização de panic de `Bytes`**: erros de `Bytes.fromList` apontam para o `(` da
  chamada (como o `NativeError` do tree-walk) e erros de método (`slice`, `concat`) usam o
  token do nome, em vez de linha/coluna 0.

## [1.2.0] - 2026-11-20

### Adicionado

- **Empacotamento MCP:** `server.json` para o MCP Registry (`io.github.loxia-lang/loxia`,
  pacote PyPI `loxia`, transporte stdio), `mcp-name` no README e instruções `uvx`/Inspector
  em [`docs/tech/mcp.md`](docs/tech/mcp.md). A 1.2.0 é a primeira versão de PyPI com o
  servidor MCP; a 1.1.0 foi publicada antes dele.

- **Localização de falha em exceções capturadas** ([ADR-0120](docs/adr/0120-localizacao-de-falha-em-excecoes.md),
  issue [#11](https://github.com/loxia-lang/loxia/issues/11)): `e.site` expõe
  `arquivo:linha:coluna` (relativo) da chamada que lançou a exceção, nos dois motores.
  `std.test` reporta a linha do `expect` no TAP (`# at ...`) e em `tests[].location` no
  JSON. Sem mudança de sintaxe.

- **Protocolo v2 do `loxia test`** ([ADR-0096](docs/adr/0096-testes-biblioteca-e-runner.md)):
  `std.test` emite eventos JSON com nonce (`start`/`result`/`discover`/`end`); o runner
  renderiza TAP/JSON e não confunde `print` do teste com resultado. `--require-tests`
  (exit 5) evita falso verde, `--capture` inclui o stdout da falha, e o relatório ganhou
  `command`, `success`, `exit_code`, `kind`, `location` e `output`
  ([`docs/tech/test-report.md`](docs/tech/test-report.md),
  [`schema/test-report-v1.json`](schema/test-report-v1.json)).

- **Matriz de cobertura por feature** ([ADR-0121](docs/adr/0121-matriz-de-cobertura-de-features.md)):
  `tests/features.toml` mapeia feature → goldens + nível diferencial, com snapshot
  congelado e página gerada em [`docs/tech/test-coverage.md`](docs/tech/test-coverage.md).

### Mudado

- `loxia test` exibe caminhos relativos ao CWD (não à raiz do pacote) e mata o process
  group no timeout. A suíte local ganhou `pytest-timeout`/`pytest-xdist`, o pytest foi
  para o pre-push e o teste de âncoras do site ignora `site/dist` defasado.
- **Performance e relatório do `loxia test`:** `--jobs` passa a default `min(4, CPUs)`,
  builds nativos rodam em paralelo, e o runner ganhou `--json-lines`, `--junit PATH` e
  escape de `#`/newline no TAP humano.

### Ferramentas

- **Piloto de `std.contracts`:** pós-condições de custo O(1) em `paths.normalize` e
  `convert.base64Encode`; `numeric.gcd`/`powMod` e `lists.sort` foram avaliados e
  revertidos por custo acima de 5% no interpretador. As propriedades continuam em
  `std_contracts_pilot.lx` nos dois motores. Entradas inválidas continuam `RuntimeError`.

- **CI macOS/Windows:** macOS roda a suíte não-backend como gate; Windows roda a mesma
  suíte em modo experimental (falhas de plataforma conhecidas). O backend nativo continua
  Linux-only.

- `loxia test --junit` emite JUnit XML com `time="0"`; `--json-lines` emite um evento por
  teste e um `summary` final.
- **`make coverage`**: medição de cobertura Python por branch, com `patch = ["subprocess"]`
  para incluir o CLI em subprocessos. Primeira medição local: 65%; guia em
  [`docs/tech/python-coverage.md`](docs/tech/python-coverage.md).
- **Ratchet de cobertura:** `coverage-baseline.toml` fixa pisos por módulo crítico,
  `make coverage-ratchet` falha abaixo deles (job "Coverage ratchet" no CI) e
  `make coverage-update` só sobe os pisos.
- **Ratchet expandido:** loader, primitivas de host, `source_index` e mais objetos de valor
  entraram no `coverage-baseline.toml`.
- **Fuzz do runner:** property tests para TAP, protocolo v2, JSON/JSONL e JUnit. O fuzz
  revelou que `--json-lines` com U+0085 quebrava o record em duas linhas; a saída agora usa
  escapes ASCII.
- **`loxia test --changed[=REF]`:** seleciona testes pelo grafo de imports desde `REF`
  (default `HEAD`), incluindo worktree e untracked; mudanças não-Lox/deletadas rodam tudo.
- **`loxia test --shard=INDEX/TOTAL`:** particiona a lista final de arquivos para CI.
- **Ratchet do backend Python:** `coverage-baseline-backend.toml` cobre o lowering; o job
  "Native backend" roda `make coverage-ratchet-backend` (exige libgc/llvmlite).
- **TIPOS.md atualizado:** remove as lacunas de L5/L6/T7 já fechadas e deixa só generics
  além do MVP, gaps de checker e L7. Issue #11 fechada.
- **CI de coverage:** a medição virou parte do job Unit 3.13 (com `-n 4`), removendo o job
  separado que duplicava a suíte.
- **Cache de binário nativo:** `loxia test --native` reusa executáveis por hash de conteúdo
  (projeto, implementação, compilador e flags); `--no-cache` desliga. O cache do runtime
  continua separado.
- Triagem de frescor de 2026-11-20 registrada em [`docs/log.md`](docs/log.md); o teste de
  âncoras do site ignora `site/dist` defasado.

- **`fs.open` com handles e erro de host em `Result`** ([ADR-0119](docs/adr/0119-fs-open-handles-e-erro-de-host.md),
  issue [#16](https://github.com/loxia-lang/loxia/issues/16)): `fs.open/read/write/close`
  no kernel (4 primitivas), `std.fs.File` + `withOpen[T]` com `FileError.kind` estável,
  modos `r`/`w`/`a`, leitura em fronteira UTF-8 e `close` idempotente. `appendText` deixa
  de reler o arquivo. **Breaking:** `readText`/`readLines`/`writeText`/`appendText`/
  `listDir` agora devolvem `Result[T, FileError]` (sem bump de major; não há consumidor
  externo). `seek`/`tell`/`+modos`/binário ficam adiados com gatilhos.

- **`std.proc` em `Result`** ([ADR-0119](docs/adr/0119-fs-open-handles-e-erro-de-host.md)):
  `spawn`/`run`/`Stream.read`/`Stream.write`/`close` e `Process.wait`/`close` devolvem
  `Result[T, ProcError]` (`spawnFailed`, `pipeClosed`, `closed`, `timeout`, `io`); timeout
  deixa de ser `nil` e `close` fica idempotente. **Breaking:** chamadas antigas precisam
  de `match`/`std.results`.

- **`csv.parseResult` e `timex.parseIsoResult`** ([ADR-0119](docs/adr/0119-fs-open-handles-e-erro-de-host.md)):
  erros de parse ganham `CsvError`/`TimeError` com `kind` estável; `parse`/`parseIso`
  continuam devolvendo `T?` como atalho legado.

- **LSP: navegação, robustez e hierarquia de tipos** ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md),
  [ADR-0114](docs/adr/0114-ast-recuperada-para-tooling.md); issue
  [#46](https://github.com/loxia-lang/loxia/issues/46)): `textDocument/references` e
  `documentHighlight` reusam as referências do resolver e o índice do rename;
  `typeDefinition`/`implementation` e `typeHierarchy/*` cobrem classes e interfaces;
  W1001/W1002 ganham `DiagnosticTag.Unnecessary`; `source.fixAll.loxia` aplica os fixes
  `safe`; a AST recuperada do parser mantém hover/definition no prefixo de um arquivo com
  erro de sintaxe; buffers não salvos alimentam o loader (importadores rechecados);
  `workspace/willRenameFiles` reescreve imports; e o `diagnosticProvider` anunciado sem
  handler de pull foi removido, com teste de drift capability↔handler. Testes em
  `tests/test_lsp_navigation.py`.

- **Protocolo stdio em Lox puro** ([ADR-0113](docs/adr/0113-protocolo-stdio-jsonrpc-framing-documents.md)):
  `std.jsonrpc` valida e constrói envelopes JSON-RPC 2.0; `std.framing` lê e escreve
  `Content-Length` sobre um reader injetado, contando bytes UTF-8 e com caps de 8 KiB/16 MiB;
  `std.documents` guarda documentos full sync com URI opaca e versão crescente. `std.json`
  ganhou `parseResult`/`JsonResult` (separa `null` de JSON malformado) e o harness
  `tests/test_protocol_lox.py` fala o protocolo com stdin binário real; os três módulos
  entram no diferencial (t3).

- **Servidor MCP** ([ADR-0112](docs/adr/0112-mcp-servidor-stdio.md)): `loxia mcp` e
  `loxia-mcp` falam MCP 2026-07-28 modern-only em stdio, sem dependência; tools
  `loxia_check`, `loxia_run`, `loxia_ast`, `loxia_spec`, `loxia_explain` e
  `loxia_version`, com paridade CLI×MCP. `loxia run --sandbox` nega fs/process e o
  servidor aplica timeout, process group e limites de processo; testes em
  `tests/test_mcp.py` e `tests/test_cli.py`.

- **Índice determinístico da documentação** ([ADR-0111](docs/adr/0111-indice-de-documentacao.md)):
  `make docs-index` gera `loxia/_spec/index.json` (spec + stdlib, 33 páginas/542 seções) e
  `site/public/llms.txt`; IDs, âncoras e URLs são os mesmos do Starlight, os links viram
  URLs canônicas e não há timestamp/caminho absoluto. O índice viaja no wheel, é validado
  por `loxia/docs_index.py` (`section`/`find_page`/`search`) e tem gate de sincronia em
  `tests/test_docs_index.py`; o site compartilha `tools/docs_common.py` com o gerador.

- **LSP: completion herdada, signature importado e inlay hints** (ADR-0090): completion
  inclui campos/métodos de superclasse e de interfaces implementadas; `signatureHelp`
  resolve funções, métodos e construtores importados/herdados sem vazar nomes mangled;
  `textDocument/inlayHint` mostra o tipo inferido de `val`/`var`/campos sem anotação e de
  variáveis de `for`. Duas settings novas (`loxia.inlayHints.enabled` e
  `loxia.completion.inheritedMembers`, default `true`) são negociadas por
  `initializationOptions`/`workspace/didChangeConfiguration`, e o cliente VS Code ganhou
  o provider de inlay hints. O ADR-0090 prometia um teste de paridade que não existia:
  `publishDiagnostics` agora é comparado com `check --error-format=json` em
  `tests/test_lsp.py`.

- **LSP: rename cross-file semântico** (ADR-0090): a AST resolvida pelo `ModuleLoader`
  identifica a declaração top-level e só os usos que pertencem a ela; um `foo` local em
  outro arquivo não é tocado. Imports, aliases e `mod.nome` são editados com precisão;
  colisão de nome ou parse error recusa o rename inteiro. `ClassTy` ganhou um `token`
  opcional de parser (`compare=False`) para atualizar anotações de tipo sem mudar
  igualdade/hash. Cobertura nova em `tests/test_lsp.py` (homônimo, alias, namespace,
  tipo e colisão) e em `tests/test_parser.py` (token sem regressão de igualdade).

- **Contratos como biblioteca** ([ADR-0108](docs/adr/0108-contratos-como-biblioteca.md)):
  `std.contracts` traz `ContractError` (distinto de `RuntimeError`), `require`/`ensure`/
  `checkInvariant`, `check`/`checkMethod` e as variantes `checkVoid`/`checkMethodVoid`;
  `old` é um local capturado e `result` é o parâmetro de `post`. O mesmo predicado serve
  de contrato de runtime e oráculo de property tests; a sintaxe de
  `requires`/`ensures`/`invariant` continua adiada com gatilhos.

### Mudado

- **CLI: help per command and split modules** ([ADR-0110](docs/adr/0110-help-do-cli-e-modulos.md)):
  `loxia --help` lists the commands and global options; each subcommand documents only
  its own flags, grouped, with examples. The compatibility mode (`loxia [flag]
  file.lx`) keeps parsing the legacy flags and is summarized in the epilog.
  `loxia/cli.py` was split into `cli_args.py`, `cli_commands.py` and `engine.py`;
  `Loxia` exposes `use_file`/`sources`/`flush` and the dead `run_file` is gone.

- **Editor: cliente VS Code em repo próprio e grammar como asset** (ADR-0109): o cliente
  saiu de `editors/vscode/` para `loxia-lang/loxia-vscode` (TypeScript + esbuild, testes
  unitários e smoke de integração, CI, VSIX, Marketplace/Open VSX). A grammar gerada
  passou para `editors/grammar/` (`loxia.tmLanguage.json`, `loxia.mjs`, `loxia.ts`) e o
  release do main anexa os três arquivos + `SHA256SUMS`; o repo novo pina a release em
  `grammar.lock.json` (versão + SHA-256) e sincroniza por `npm run grammar:sync`, sem
  submódulo e sem cópia manual. O servidor LSP continua no main (ADR-0090). O cliente
  ganhou play button interpretado/compilado, settings por feature, autodetecção do CLI e
  testes; `editors/README.md` foi reescrito para o contrato de asset.
- **`make grammar-assets`**: `editors/build_grammar.py --assets DIR` grava os três
  artefatos e `SHA256SUMS` para o release; `--check` continua sendo o gate de drift.

### Corrigido

- **`std.timex.parseIso` rejeita sinais em campos ISO**: `_digits` agora valida
  dígitos ASCII de largura fixa em vez de delegar ao `Int.parse` (que aceita `+`/`-`);
  `+123-01-01` e `2024-01-01T-1:00:00Z` voltam a ser `nil`.
- **`std.fs` rejeita caminhos com NUL nos dois motores**: as primitivas de mutação,
  `fs.open`, `fs.exists` e `fs.listDir` não derrubam mais o Python com `ValueError`;
  o C também não trunca silenciosamente o caminho. O `kind` é `io`.
- **`std.fs.rename` mantém o mesmo `kind` no tree-walk e no binário** para
  `ENOTEMPTY`/`EEXIST` (`notEmpty`/`alreadyExists`).

- **Backend: `super` em lambdas/funções locais e bindings de `match` capturados**
  (ADR-0022): o passe de captura agora marca o receptor de `super` e declara os bindings
  de pattern; funções internas herdam a classe léxica e o binding vira célula. Antes o
  `--check` passava e o lowering nativo falhava com `E4002` (`super_in_closure.lx`,
  `match_capture.lx`).
- **fs: `read(n)` respeita o teto de bytes e mantém UTF-8 pendente**: o tree-walk
  devolvia até 4 bytes extras por chamada e descartava `pending`; agora espelha o runtime
  C, e `tests/test_fs_runtime.py` cobre `é` com `read(1)`/`read(2)`.
- **fs/proc: handles não sobrevivem a uma execução**: `Interpreter.interpret` fecha as
  tabelas no `finally`; `FileTable.close_all` existia sem chamador e handles antigos
  continuavam legíveis na execução seguinte.
- **`loxia test --changed` com `loxia.toml`**: a seleção passa a resolver imports na raiz
  do manifest e em `modules.paths`, não no diretório do teste.
- **Cache nativo do `loxia test`**: a chave inclui dependências `path`/cache git e
  manifestos/locks, evitando falso verde depois de mudar uma dependência externa.
- **`std.framing.readFrame`**: um reader que devolve `""` (sequência UTF-8 pendente)
  agora falha com `truncated` em vez de girar para sempre.

- **Backend: payload `Nil` no `match` de `Result`** ([ADR-0113](docs/adr/0113-protocolo-stdio-jsonrpc-framing-documents.md)):
  `Result[Nil, E]` passava no `--check` e o lowering nativo falhava com `E4002` ao ligar o
  payload `nil` do braço. O braço agora usa um slot dummy e carrega `Value(NIL)`; regressão
  em `tests/cases/result_nil.lx` (l6).
- **Backend: `this` lexical em lambdas e funções locais** (ADR-0022): o receptor agora é
  capturado em célula quando uma função interna o usa, cobrindo lambda direto, closure
  retornada e função local (`tests/cases/this_in_lambda.lx`). Antes o `--check` passava e
  o lowering nativo falhava com `E4002`.
- **Backend: `Nil` em parâmetro de tipo de função e em local**: `Nil` ganhou um slot
  `i32` sem payload, permitindo `check[T]` com `T = Nil` e `val x = nil`
  (`tests/cases/nil_value.lx`); parâmetro nomeado `Nil` continua recusado pelo checker.
- **Backend: captura de locais dentro de `try`/`raise`**: o passe de captura percorre
  corpo, handlers e `finally`, então closures dentro de `try` enxergam os locais
  capturados no binário nativo (`tests/cases/std_contracts.lx`).

## [1.1.0] — 2026-11-17

### Adicionado

- **Fuzzing do front-end** (TODO §7/§14.0): `hypothesis` como dependência de dev e
  `tests/test_fuzz.py` com propriedades determinísticas — texto arbitrário e sopa de tokens
  nunca derrubam scanner/parser, posições ficam dentro da fonte e duas execuções produzem
  os mesmos bytes; `make fuzz` roda a suíte. O CI padrão já executa os exemplos fixos.
- **Orçamento de monomorfização (M8)** ([ADR-0063](docs/adr/0063-orcamento-monomorfizacao.md)):
  teto determinístico de 256 funções especializadas, 256 layouts de classe, profundidade 8
  e nome mangled de 1024 bytes, com `E4003`/exit 65 e sem artefato parcial. `make monomorph`
  mede o corpus (máx. 15 funções/4 classes) e o sintético (256 = 1,2 MiB/~0,33 s); o teto
  fica ~17x acima do corpus.

- **Scaffolding `loxia new`/`init`** ([ADR-0106](docs/adr/0106-scaffolding-new-init.md)):
  cria o projeto mínimo e determinístico (`loxia.toml`, `.gitignore`, `src/main.lx` e um
  `loxia.lock` vazio), com `git init` por padrão (`--no-git` desliga, nunca repo aninhado),
  nome normalizado/`--name`, `--json` e erro `C0003` para alvo/estado inválido.

- **Dependências `git`** (fase 2 do §14.7, [ADR-0105](docs/adr/0105-dependencias-git.md)):
  `acme = { git = "...", rev = "..." }` com commit completo ou tag (branch nunca), lock com
  `commit` resolvido (tag móvel não muda o build) e `version` obrigatória no manifest da
  dependência. Mirror bare + checkout limpo (`git archive`, sem `.git`/hooks/submódulos) em
  `.loxia/cache`, `loxia fetch`/`--offline` e `run`/`check`/`build` sem rede; URL e `rev`
  validados (`ext::` e `-x` recusados) e `examples/monorepo/` compila nos dois motores.

- **Lock de dependências (`loxia.lock`) e modo `--frozen`** (fase 1 do §14.7,
  [ADR-0104](docs/adr/0104-lock-e-frozen.md)): `loxia lock` grava o lock canônico (nome,
  `path` relativo, `[package].version` `X.Y.Z` e `sha256` da árvore `.lx`), `lock --check`
  detecta drift (exit 1), `fetch` verifica a árvore e `--frozen` resolve só pelo lock
  (`C0002`, exit 65) em `run`/`check`/`build`/`ast`/`test`. `--offline` proíbe rede,
  `--cache-dir` seleciona o cache (default `.loxia/cache/`) e `loxia test` repassa as
  flags aos subprocessos. `run`/`check`/`build` nunca acessam a rede.

- **`loxia repl` e distribuição verificada** (Fase 0 do §14.7 e item 1 do §14.4):
  o REPL ganhou subcomando próprio (`loxia repl`, com `--debug`, `--module-path` e
  `--json-lines`), e o banner/prompt só aparecem em TTY — pipe e agente recebem apenas a
  saída do programa. `pytest -m install` passa a policiar o layout do artefato (sdist com
  `std/` na raiz, wheel com `loxia_core/std/`, nunca os dois) e o CI roda o teste no job do
  wheel. README documenta o comando instalado (`pip install loxia`/`uv tool install loxia`)
  a partir da 1.1.0.

- **Documentação como site** ([ADR-0103](docs/adr/0103-site-de-documentacao-e-versionamento.md)):
  Astro Starlight em `site/` construído a partir de `docs/` (`tools/docs_site.py`), com
  inglês na raiz, pt-BR em `/pt/`, referência 1.1 em inglês, arquivo congelado da 1.0 e
  deploy no GitHub Pages em <https://loxia-lang.github.io/loxia/>. Inclui
  home/why/learn/cookbook, checagem de links do HTML, `translated_from` e job `site` no CI.
- **`std.property.listOf[T]`** ([ADR-0098](docs/adr/0098-property-based-testing.md)):
  gerador genérico de lista; `listOfInt`/`listOfString` ficam como aliases. O lowering
  agora propaga o `type_subst` do corpo genérico para lambdas aninhadas, fechando o
  `E4001` de `Gen[List[T]]` (`Unbound type parameter 'T'`). Golden `std_property` e
  diferencial nos dois motores.
- **E3004 — fix de anotação ausente**: parâmetro com default literal e `return` com
  literais iguais ganham fix com o tipo exato; `safe` em função local/lambda e `unsafe`
  em API pública. Sem tipo exato (parâmetro sem default, campo sem inicializador,
  `return` não literal ou tipos discordantes) não há fix. `loxia fix` aplica só os
  locais; `docs/tech/fixes.md` atualizado.
- **Módulos e dependências `path`** ([ADR-0100](docs/adr/0100-dependencias-path.md)):
  `loxia.toml` descoberto no ancestral mais próximo, `[dependencies] nome = { path = ... }`
  resolvido pelo nome do pacote, `[modules].paths` para raízes soltas e `--module-path`
  repetível. Dependência importa o próprio pacote (`acme.foo`) e não vê o projeto;
  ambiguidade e raiz inexistente viram erro com caminho relativo. `..` continua proibido
  no `import`; tree-walk e backend usam a mesma resolução.
- **Notes de proveniência** ([ADR-0099](docs/adr/0099-notas-de-proveniencia.md)):
  erros de tipo cujo valor é `Variable`/`Get`/`Index`/`Call` ganham
  `note: the value comes from \`expr\` (line N)`, com o texto vindo do `SourceIndex`
  (agora no core) e do `SourceMap` (módulos incluídos). Literais e expressões compostas
  não ganham nota; `json` expõe `notes[]` e `--error-format=short` continua uma linha.
- **Completion do LSP**: AST original em vez da reescrita — locais/parâmetros do escopo,
  imports (`import`/`from`), membros de módulos std/usuários, `this`/`super`, variantes
  de enum, membros nativos (`Int.`/`math.`) e métodos de lista/mapa; sem nomes mangled.
- **Tooling de editor**: formatter com `fn` canônico em método e trailing comma
  multiline (parser aceita; golden `trailing_comma`); `workspace/symbol` no LSP; cliente
  VS Code sem dependências em `editors/vscode/` (diagnostics, hover, definition,
  completion, signature, formatação, code actions, rename e símbolos).
- **Fixes restantes**: E2001 (rename do binding duplicado + usos), E3016/E3018
  (default primitivo/opcional), E3002 (remoção de argumentos extras) e E3015
  (rename de método), todos `unsafe`.
- **Spans de expressão**: `loxia_core/frontend/source_index.py` (offset → menor
  expressão) e rename cross-file conservador no LSP para declarações top-level.
- **LSP rename**: `textDocument/prepareRename` e `textDocument/rename` para variáveis
  locais/parâmetros (mesmo arquivo, via `SymbolIndex.references`); cross-file/globais
  continuam fora.
- **W1002/E2002/E2009** ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)):
  import não usado (`safe`, remove a linha; pureza estrutural de módulo), `val`→`var`
  local (E2002) e campo (E2009), ambos `unsafe`.
- **Fixes + `loxia fix` + `codeAction`** ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)):
  W1001 (`safe`, renomeia para `_unused_N`) e E3003 (`unsafe`, did-you-mean); o LSP
  publica `data.fixes` e responde `textDocument/codeAction`; `loxia fix` aplica só
  `safe`, com dry-run/`--apply` e reparse/check a cada rodada.
- **Property-based testing** ([ADR-0098](docs/adr/0098-property-based-testing.md)):
  `std.property` com `Gen[T]`, `forAll`, geradores, shrinking e seed determinística.
- **Stdlib T3**: `std.rand` (xorshift64* com semente, `int`/`float`/`bool`/`shuffle`),
  `std.log` (níveis em stderr, sem timestamp), `std.hash` (FNV-1a 32/64 e djb2 sobre
  bytes UTF-8), `std.collections` (Stack/Queue/Deque/PriorityQueue) e `std.timex`
  (datas UTC: `iso`, `parseIso`, `daysFromCivil`, `civilFromDays`, `addDays`, `parts`).
- **Ranges inclusivos `..=`** ([ADR-0097](docs/adr/0097-ranges-inclusivos.md)):
  `a..=b` inclui o fim, com a mesma precedência de `..`, sem passo; `Range` compara e
  imprime `inclusive`, e `INT_MAX..=INT_MAX` roda uma vez sem wrap.
- **`std.iter`**: `enumerate`, `zip`, `sum`/`sumFloat`, `contains`, `any`, `all`,
  `find` e o enum `Step[T]` para iterar elementos `nil` via `next() -> Step[T]?`.
- **Backend**: método que retorna a própria classe (padrão `iter() -> Self`) e cadeia
  de métodos não avaliam o receptor duas vezes; `print("DEBUG match")` removido do
  lowering de enums.
- **Hooks e isolamento por teste** ([ADR-0096](docs/adr/0096-testes-biblioteca-e-runner.md)):
  `std.test` ganhou `beforeEach`/`afterEach` escopados ao `describe` (ordem externa→interna
  e inversa no `after`, mesmo em falha) e `--list` (só nomes); o runner ganhou
  `--isolate=test`, que descobre nomes com `--list` e roda um subprocesso por teste
  (`--only`), com `--jobs` processos em paralelo e timeout por teste.
- **R3 e R4 corrigidos**: a variável do `for-in` preserva a assinatura de função
  (closure em lista chamável no binário) e `except` de classe de módulo compara o
  ponteiro do descritor, casando nos dois motores; golden `closure_in_list.lx` (`l4`)
  e regressão em `tests/test_module_exceptions.py`.
- **Testes** ([ADR-0096](docs/adr/0096-testes-biblioteca-e-runner.md)): `std.test`
  (`Suite` com `describe`/`it`/`skip`/`report`/`done`, matchers híbridos, `Recorder`,
  TAP determinístico) e `loxia test` (descoberta de `tests/**/*_test.lx`, um subprocesso
  por arquivo, `--filter`/`--only`/`--jobs`/`--timeout`/`--json`/`--native`/`--fail-fast`).
  Sem reflection/registry (`R3`); `R4` registrado para exceção de classe de módulo.
- **Processos, streams e `poll`** ([ADR-0095](docs/adr/0095-processos-streams-poll.md)):
  kernel `process.*` (`spawn` sem shell, `stdin`/`stdout`/`stderr`, `read`/`write` em
  pipes com fronteira de UTF-8, `wait`/`kill`/`close` e `poll`) e `std.proc`
  (`Stream`, `Process`, `Output`, `spawn`, `run` com drenagem concorrente e timeout).
  POSIX e ambiente; kernel 19 → 29. `std.utf8` (`byteLen`, `utf16Len`, `utf16Column`)
  fecha as duas unidades de posição que um protocolo precisa.
- **Runtime C em unidades + ABI gerada** ([ADR-0071](docs/adr/0071-primitivas-de-runtime.md)):
  `runtime/runtime.c` virou `core`, `objects`, `strings`, `containers`, `numeric` e
  `kernel` com um header comum (`lox_runtime.h`); o driver compila cada unidade e
  cacheia os `.o` por chave de todas as fontes/headers. Nenhum byte gerado muda.
  `runtime/kernel_gen.h` é gerado de `primitives.py` (`make primitives`) e incluído pelo
  `kernel.c`: a assinatura C de uma primitiva não diverge mais da tabela em silêncio.
- **Kernel de stdio por bytes** ([ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md)):
  `io.flush()` (força stdout/stderr) e `io.readUtf8(n)` lê exatamente `n` bytes de stdin em
  UTF-8 estrito (`""` para `n == 0`, `nil` só no EOF imediato, `RuntimeError` com a posição
  da chamada para `n < 0`, EOF no meio ou bytes inválidos). Kernel vai de 17 para 19
  primitivas. A tabela ganhou `site`: primitivas falíveis recebem `(line, column)` no
  símbolo C, então o panic do binário aponta a chamada. Habilita framing de protocolo por
  stdio (LSP/JSONL/MCP) em Loxia.

- **Modelo de fix estruturado** ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)):
  `Fix`/`Edit`/`Applicability` no `Diagnostic`, com `fixes[]` no envelope JSON
  (`safe`/`unsafe`, `span` + `new_text`). **Nenhum produtor emite fixes ainda**; a análise
  de quem pode produzir e com qual confiabilidade está em
  [`docs/tech/fixes.md`](docs/tech/fixes.md).
- **Docs da stdlib e builtins** ([ADR-0091](docs/adr/0091-doc-comments-e-geracao-de-docs.md)):
  doc comments `///` em toda a API pública de `std/*.lx`, registry de builtins em
  `loxia/builtins_docs.py` e `docs/stdlib/` gerado (índice, 15 módulos e builtins) por
  `docs/_hooks/stdlib.py`; `make stdlib-docs`/`docs-sync` e teste de cobertura.
- **LSP-0** ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)): `loxia lsp` em Python,
  JSON-RPC sobre stdio sem dependências, `initialize`/`shutdown`/`exit`, full sync
  `didOpen`/`didChange`/`didClose`, `publishDiagnostics` com code/severity/range/
  relatedInformation/help/trace e `documentSymbol` (classes, métodos, campos, enums,
  variantes, interfaces, funções e variáveis). **LSP-1 básico**: `SymbolIndex` +
  `Resolver.references` para `hover` (assinatura/tipo/doc) e `textDocument/definition`
  de variáveis, funções, classes, campos/métodos e variantes. **LSP-2 parcial**:
  completion (global e por membro), signatureHelp, documentFormatting (via `loxia fmt`)
  e semanticTokens/full. Code actions/fixes, rename e spans formais ficam pendentes.
- **Estilo e formatter mínimo** ([ADR-0092](docs/adr/0092-estilo-e-formatter.md)):
  `docs/guia-estilo.md` normativo e `loxia fmt` Python (indentação de bloco, `;` de fim de
  linha, newline final, preservação de strings/comentários), com `fmt --check` (exit 1 se
  mudaria) e `fmt --stdin`. `fn` em método, trailing comma, reflow e dogfood Lox ficam
  pendentes.
- **Doc comments `///` e `loxia doc`** ([ADR-0091](docs/adr/0091-doc-comments-e-geracao-de-docs.md)):
  doc Markdown anexada a funções/métodos, classes, interfaces, enums/variantes, campos,
  type alias e `val`/`var`; `loxia doc arquivo [--json]` gera a referência sem executar o
  programa. A grammar TextMate ganhou o scope de doc; a spec léxica documenta o vínculo
  (linha em branco quebra). Docs obrigatórias da stdlib/builtins e geração do site ficam
  pendentes.
- **CLI agent-friendly (core)** ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)):
  subcomandos `run`/`check`/`build`/`ast`/`explain`/`capabilities` (flags antigas
  preservadas), `--json`/`--json-lines` (`start`/`diagnostic`/`summary`), `--stdin` +
  `--file-name`, `--timeout` em `run`/`check` (exit `124` + `C0001`), `--watch` restrito a
  `check` e `-Werror`/`W1001` (local não lido) em `check`/`build`, nunca em `run`.
  `capabilities --json` publica versão, comandos, códigos e limites; `explain <code>`
  consulta o catálogo. `fixes[]`/`loxia fix`, `W1002`, `fmt`, `doc` e `lsp` ficam pendentes.
- **Diagnósticos com labels e sugestão**: `E2001`/`E2002` apontam a declaração anterior
  (`- first declared here`) e `E3003` ganha `help: did you mean '…'?` com candidatos
  visíveis ordenados. `human` renderiza o segundo trecho, `note:` e `help:`; `short`
  continua uma linha; JSON já expunha os campos.
- **Diagnósticos: fonte do módulo e stack trace de runtime** ([ADR-0089](docs/adr/0089-stack-trace-de-runtime.md)):
  erro de compilação e de runtime em módulo aponta o arquivo do módulo (`Token.file`), e
  todo erro de runtime não capturado imprime frames default-on no formato
  `  at <nome> (<arquivo>:<linha>:<col>)`, com os 5 frames mais internos + 5 mais externos
  e elisão acima de 10. O binário reproduz o mesmo stderr (I1). `R1015` ganhou a posição
  da declaração; `--error-format=json` expõe `trace` e `short` omite os frames.
- **Distribuição**: `pip install loxia` / `uv tool install loxia` entrega o comando `loxia`,
  a stdlib e o `runtime.c` no wheel (hatchling, `force-include`; resolução em
  `loxia_core/bundle.py`). `tests/test_install.py` (`pytest -m install`) prova o layout
  instalado fora do repo; release no PyPI via Trusted Publishing
  ([ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md)).

- **Limite de pilha** ([ADR-0077](docs/adr/0077-limite-de-pilha.md)): 10.000 chamadas
  Lox ativas nos dois motores, erro `R1015`/`Stack overflow.` capturável por
  `try`/`except RuntimeError`, restauração da profundidade em `try`/`finally` e reserva de
  pilha no binário via `setrlimit`. Chamadas nativas e construtores de exceção embutida
  não contam; construtor + `init` contam duas ativações.
- **Heap default de 512 MiB + `--max-heap`** ([ADR-0087](docs/adr/0087-heap-cap-e-self-hosting.md)):
  o hard cap do binário subiu de 128 MiB para 512 MiB e `--emit=exe --max-heap=SIZE`
  embute outro teto no runtime (default `512M`, faixa `32M..8G`). I1 continua até 64 MiB
  de memória viva; o teste de OOM usa um build de 128 MiB e um caso novo prova os 512 MiB.
- **Stdlib T2 completa** ([ADR-0079](docs/adr/0079-stdlib-t2.md)): `std.json`
  (`parse`/`stringify`/`pretty`, ordem de inserção e `Int`/`Float` distintos), `std.fmt`
  (`format`/`pad`/`commas`/`fixed`/`percent`/`bytes`), `std.paths` (POSIX lexical),
  `std.fs` (`readText`/`readLines`/`writeText`/`appendText`/`exists`/`listDir`),
  `std.io` (`write`/`writeErr`/`readLine`/`readAll`/`prompt`), `std.cli`
  (`parse`/`flag`/`option`/`positional`/`usage`), `std.sets` (`Set[T]`), `std.csv`
  (RFC 4180) e `std.convert` (base64/hex sobre UTF-8), com golden, `--check` e corpus
  `t2`. Kernel ganhou `io.readAll`, `fs.exists` e `fs.listDir` (teto 15 → 17, todos
  `ambient`); classes passam a aceitar campos `List`/`Map`/tupla/`Range`/enum, `str(Any)`
  funciona no backend e o runtime C valida chave de `Map` (`R1014`) como o interpretador.
  Exemplo novo: [`examples/sales.lx`](examples/sales.lx).
- **Stdlib T1 completa**: `std.maps` (`Map[String, V]`: `entries`, `fromEntries`,
  `merge`, `pick`, `omit`, `mapValues`, `filterKeys`, `filterValues`, `invert`,
  `hasValue`, `getOr`, `toList`), `std.numeric`, `std.asserts` e `std.results`, com
  golden, `--check` e casos no corpus `t1`; `std.strings` e `std.lists` já estavam.
- **Diagnósticos estruturados** ([ADR-0075](docs/adr/0075-diagnosticos-estruturados.md)):
  modelo único de `Diagnostic` (código de família, fase, severidade e span com
  linha/coluna/offset em bytes), renderizadores `human` (cabeçalho + caret), `short` e
  JSON v1, ordenação/dedup/limite determinísticos e caminho de exibição relativo. Flags
  novas: `--error-format`, `--color` e `--max-errors`. Catálogo em
  [`docs/spec/erros.md`](docs/spec/erros.md). O runtime humano continua no formato do livro
  até a paridade nativa.
- **GC Boehm (M7)** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)): a arena
  de 64 MiB foi substituída por heap coletado (`libgc`), com hard cap de 128 MiB e I1 até
  64 MiB de memória viva; programas que alocam em laço deixam de morrer no teto. O ponto
  exato do `Out of memory.` não é determinístico (coletor conservador), mas canal,
  mensagem e exit code são.
- **Verificação de IR (`mod.verify`)** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)):
  o driver verifica o módulo LLVM antes de emitir `.ll`, `.o` ou executável; IR inválido
  vira `BackendError` (exit 65) com mensagem determinística, nunca binário quebrado.
- **`not` substitui `!`** ([ADR-0068](docs/adr/0068-not-substitui-bang.md)): negação no
  nível unário com a mesma precedência; `!` sozinho agora é diagnóstico dirigido
  (`use 'not' for negation`) e `!=` continua. Quebra deliberada de quem usava `!`.
- **Destructuring aninhado** ([ADR-0069](docs/adr/0069-destructuring-aninhado.md)):
  `val (a, (b, c)) = t`, com anotação recursiva e erros por nível; corrige também a
  captura por closure de nomes destruturados no backend (furo do I4).
- **Strings `"""` e raw** ([ADR-0070](docs/adr/0070-strings-multilinha-e-raw.md)):
  `"""..."""` é a forma canônica de multilinha (aspas livres, sem dedent/newline mágico);
  `r"..."`/`r"""..."""` desligam escapes e interpolação. `"..."` passa a ser de uma linha.

- **Gate e orçamento sintático** ([ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md)):
  toda sintaxe nova passa por quatro perguntas (substituição, decidibilidade local,
  precedência, forma canônica), orçamento de superfície e lista de não-objetivos; o agente
  pergunta ao humano antes de ampliar a gramática. Procedimento na skill `lox-syntax`.
- **Desambiguação sintática** ([ADR-0067](docs/adr/0067-desambiguacao-sintatica.md)):
  `//` onde se espera expressão e mapa no início de statement ganham diagnóstico dirigido;
  operador pode iniciar a linha dentro de `()`, `[]` e `{}` de expressão; `fn` é opcional
  em método; união no lado direito de `is` exige parênteses (`x is (Int | String)`).
- **I4 — `--check` limpo compila** ([ADR-0059](docs/adr/0059-i4-check-limpo-compila.md)):
  o checker é a fonte única dos tipos; um programa aceito no `--check` não pode falhar no
  `--emit` por tipo/coerção, só pela lacuna declarada. Gate novo em `tests/test_backend.py`
  varre o corpus inteiro.
- **Orçamento de memória como contrato** ([ADR-0060](docs/adr/0060-orcamento-de-memoria.md)):
  arena de 64 MiB sem `free` documentada em `docs/spec/garantias.md` e teste que prova a
  falha determinística (`exit 70`, `Out of memory.`) e a assimetria com o interpretador.
- **Gate de documentação** (`tests/test_docs_consistency.py`, `docs/_hooks/`): ADR com
  numeração única/sequencial e no índice, página de spec com `sources:` que casam com
  arquivos reais, flags do CLI cobertas pelo README, bloco de níveis **gerado** do
  manifesto e lista de frases defasadas proibidas. Frescor derivado do git com ledger em
  `docs/log.md` (skill `lox-docs`).

- Backend **generics com lambda contextual**: checker publica o `FnTy` concreto da lambda em argumento genérico; `generics.lox` promovido.
- Backend **`is` com união parentetizada**: `x is (Int | String)` compara tags/classes e fecha `is_union_parens.lox`.
- Stdlib **T1**: `std.lists.sort` estável (comparador de 3 vias), `zip`, `flatten`, `flatMap`, `unique`, `chunk` e `partition` ([ADR-0076](docs/adr/0076-std-lists-sort.md)).
- Stdlib **T1 (base)**: `std.strings` e `std.lists` em Lox sobre as primitivas; casos `t1` no corpus.
- Imports/módulos: arquivo=módulo, pasta=namespace, `_` privado verificado, `from`/`as`, desugar e display preservado.
- Kernel **13.2**: `args`, `io.*`, `os.*`, `time.*` e `main(argc, argv)`; tabela única cobre as 14 primitivas.
- Kernel **13.3/13.4**: cache preguiçoso de code points no `LoxStr`, `substr`/`join`/`charCodeAt`/`fromCodePoint` e tabela única de primitivas ([ADR-0071](docs/adr/0071-primitivas-de-runtime.md)); `bench/cases/string_scan.lox` cai para 9,1 ms no nativo.
- Backend **L7b (parte)**: passes de IR `-O2` antes de emitir objeto e `make bench-native`
  com speedup contra o baseline do interpretador; `returns_twice` no `_setjmp`.
- Backend **L6k — função genérica como valor**: lambda genérica especializada no call site (`val id = fn(x) => x; id(1)`), com cache e unboxed; `generic_lambda_value.lox` promovido.
- Backend **L6j — exceções/unwinding**: frames `setjmp`/`longjmp`, `try`/`except`/`finally`, `raise`, classes sintéticas `Exception`/`LoxRuntimeError` e erros de runtime capturáveis; `exceptions.lox` promovido ([ADR-0062](docs/adr/0062-l6-excecoes-unwinding.md)).
- Backend **L6i — enums/`match`/`Result`**: `LoxEnumValue` com descritor, construtores de variante, `match` por variante, igualdade/print e tag `ENUM`; `enums.lox` e `result.lox` promovidos ([ADR-0061](docs/adr/0061-l6-enums-match.md)).
- Backend **L6h — loop/nil/Any**: captura por iteração, variável que começa `nil` e índice de `Any`-tupla ([ADR-0058](docs/adr/0058-l6-loop-capture-uninit.md)).
- Backend **L6g — defaults como valor**: funções com parâmetros default podem ser passadas como valor; defaults são preenchidos na chamada indireta ([ADR-0057](docs/adr/0057-l6-defaults-as-value.md)).
- Backend **L6f — math e parse**: `math.*`, `Int.parse` e `Float.parse` ([ADR-0056](docs/adr/0056-l6-math-parse.md)).
- Backend **L6e — `Any`**: unbox, `is`/`as`, igualdade dinâmica e `for-in` de tupla; caso `any_casts.lox` promovido ([ADR-0055](docs/adr/0055-l6-any-casts.md)).
- Backend **L6d — tuplas e `chars`**: tuplas boxeadas com destructuring e `chars(s)` sobre code points UTF-8.
- Backend **L6d — tuplas**: runtime boxeado, literal, índice, `len`, igualdade, print e destructuring `val/var (a,b)` ([ADR-0054](docs/adr/0054-l6-tuplas.md)).
- Backend **L6c — mapas**: `Map` com chaves/valores boxeados, `get`/`has`/`remove`/`keys`/`values`, `for-in` de chaves, igualdade independente de ordem, stringify e ciclos ([ADR-0053](docs/adr/0053-l6-mapas.md)).
- Backend **L6b — listas**: `List` com elementos boxeados no runtime, literais,
  índice/atribuição, `push`/`pop`, `len`, `for-in`, igualdade estrutural, `print`/`str`/
  `repr` e ciclos; casos `list_*` promovidos ([ADR-0052](docs/adr/0052-l6-listas.md)).
- Backend **L6a — Range, `for-in` e escalares**: `Range` como valor de runtime,
  `for-in` sobre Range/String, `**`/bits/shifts e `as` numérico; casos `range_value`,
  `for_in`, `bitwise*`, `exponentiation`, `one_line_block` e `optional_semicolons`
  promovidos ([ADR-0051](docs/adr/0051-l6-range-for-in-escalares.md)).
- Backend **T7 — monomorfização de funções e classes genéricas**
  ([ADR-0050](docs/adr/0050-monomorfizacao-t7.md)): o checker publica as instanciações
  (`generic_fn_instances`, `generic_class_sites`) e o lowering gera `id$Int`, `id$String`,
  `Box$Int` etc., sem re-inferência e sem boxing. `generic_functions.lox` e
  `generic_class.lox` promovidos para o nível `t7`; containers e função genérica como valor
  seguem `PENDING`/65.
- Backend **L5c — classes locais com campos/métodos e captura**: construtor local recebe o
  descritor como argumento oculto, com layout/vtable/init próprios; classe local com
  campos, `init`, métodos, `this` e captura de variáveis externas funciona.
- **Spike L6 — `Any` boxeado/união escalar** ([ADR-0049](docs/adr/0049-any-boxeado-spike-l6.md)):
  `{i64 tag, i64 payload}` para `Any` explícito e para uniões escalares/string;
  `??` boxeia o resultado, `print` dinâmico via `lox_print_any`; `any_box.lox` e
  `nil_aware.lox` promovidos ao nível `l6`. Sem unbox/igualdade/casts gerais ainda.
- **Refactor do lowering**: `lower.py` foi dividido em `lower_model`, `lower_base`,
  `lower_functions`, `lower_variables`, `lower_optionals`, `lower_strings`,
  `lower_class_layout`, `lower_class_codegen`, `lower_instances` e `lower_calls`, sem mudança de ABI ou comportamento. A separação
  preserva as representações do ADR-0048 para a futura FFI com C.
- Backend **L5a/L5b — classes e herança** ([ADR-0048](docs/adr/0048-abi-classes-l5.md)):
  métodos `(env, this, params...)`, vtable de closures, descritor de classe, instância
  `{classe, bitmap, slots i64}`, campos `val`/`var` com bitmap de inicialização, bound
  methods, `this`, `init` (defaults no call site), `print`/`str` de classe/instância,
  herança com cópia/override de vtable, `super`/`super.init`, `init` herdado e prefixo de
  campos. `String?`/instância `T?` em campos/parâmetros/retornos usam ponteiro nulo;
  `is`/`as` de classe, classes locais **vazias** e `?.` com receptor opcional também
  funcionam (curto-circuito não avalia argumentos no nil). Classes locais gerais e o
  `nil_aware` completo ficam no L6 (união/`Any`).
- Backend **L2.5 — optionais escalares** ([ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md)):
  `Int?`/`Float?`/`Bool?` como `{i1, T}`, `var x: T?;` nascendo `nil`, `nil` contextual,
  `T?` em parâmetros/retornos/closures, `??`/truthiness/igualdade/`print`/`str`/interpolação
  e **unwrap checado** no uso (sem confiar no narrowing do checker). `var x: Int;` sem
  inicializador continua 65 até o L6.
- Backend **L4 — closures e valores de função** ([ADR-0046](docs/adr/0046-closures-celulas-l4.md)):
  funções locais e lambdas com tipo concreto, captura por **células** só para variáveis
  capturadas (`env` de ponteiros), ABI uniforme `(i8* env, params...)`, closure
  `{fnptr, env, display}`, chamada indireta, reatribuição de função e
  `print`/`str`/`repr`/interpolação de `<fn f>`/`<lambda>`. Ordem de declaração de topo é
  preservada (chamar antes vira panic 70, sem hoisting). Função com defaults como valor
  continua rejeitada com 65 no L4; spans/stack trace ficam para um ADR próprio.
- Exceções ([ADR-0042](docs/adr/0042-excecoes.md)): `Exception`/`LoxRuntimeError`
  embutidos, `class MyError(Exception)`, `raise expr`/`raise;`, `try` com múltiplos
  `except Tipo as e` e `finally`; erros de runtime capturáveis como `LoxRuntimeError`;
  uncaught exit 70. Backend rejeita com 65 até o L6.
- Enums e `match` ([ADR-0041](docs/adr/0041-enums-match.md)): `enum` com variantes e
  payload posicional, genéricos (`Result[T, E]` embutido com `Ok`/`Err`), construtores
  namespaced (`Cor.Verde`, `Shape.Circle(1.0)`), `match` expressão com bindings e `_`,
  exaustividade rígida e arms inalcançáveis; igualdade estrutural e stringify
  `Enum.Variante(...)`. Backend rejeita com 65 (L6).
- Classes genéricas ([ADR-0040](docs/adr/0040-generics-classes-desenho.md)): `class Box[T]`
  com múltiplos parâmetros, `T` em campos/métodos/`init`/`this`, `Box[Int]` como tipo,
  inferência no construtor (`Box(1)` → `Box[Int]`), argumentos invariantes e erasure no
  runtime. Métodos genéricos, herança de `Box[Int]` e `is/as` com argumentos ficam para
  depois; o backend rejeita classes com 65 (L6).
- Decisões de tipos ([ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md)): sem sufixos
  de literal (`D-2` fechado); `Float` fora das chaves de `Map`; `Option[T]` = `T?`;
  `Result` será enum/ADT com T6c; `type` alias transparente (P3); `throw` segue fatal.
- Tuplas ([ADR-0036](docs/adr/0036-tuplas-implementacao.md)): literal `(a, b)`, tipo
  `(A, B)`, índice `t[i]` (bounds de literal no `--check`; dinâmico vira união), `len`,
  igualdade estrutural, formatação `(1, "a")` e destructuring `val`/`var (a, b) = t` com
  anotação opcional. Covariantes por elemento; `for-in`, `is (A, B)` e `as (A, B)` também
  funcionam; o backend rejeita com 65 (L6).
- Strings: `chars(s)` devolve os code points como `List[String]` (acesso a caractere sem
  `s[i]`, que continua erro) e `< <= > >=` ordenam `String` por code point, no
  interpretador e no backend (`lox_str_compare`). Identificadores continuam ASCII e não há
  normalização ([ADR-0035](docs/adr/0035-strings-texto.md)).
- Checker (T4): `val f = fn(x) => x` infere parâmetros/retorno e generaliza o esquema
  ([ADR-0033](docs/adr/0033-inferencia-t3c-t4.md)); `var` não generaliza. O T3c
  (parâmetro de `fn` sem anotação) foi implementado e **revertido** por conflitar com o
  contrato explícito do ADR-0020 ([ADR-0034](docs/adr/0034-t3c-revertido.md)).
- Checker (T5): narrowing de campos e índices literais (`p.nome`, `xs[0]`, `m["k"]`), com
  invalidação ao mutar o caminho ou a raiz e refino pelo falso na saída de `while`
  ([ADR-0032](docs/adr/0032-narrowing-campos-indices.md)). Continua sem CFG/aliasing.
- Backend nativo **L0** ([ADR-0031](docs/adr/0031-backend-nativo.md)): `--emit=ll|obj|exe`
  compila `print` de `Int`/`Bool`/`nil` com `+ - * // %`, comparações, igualdade e unário
  para binário nativo, usando `llvmlite` como extra opcional (`uv sync --extra llvm`).
- Runtime C (`runtime/runtime.c`): `lox_print_int/bool/nil`, `lox_panic` (exit 70 com o
  mesmo stderr do interpretador) e as guardas de `//`/`%` (zero e `INT_MIN / -1`).
- Teste diferencial (`tests/test_backend.py`): compila cada caso, executa o binário e
  compara stdout, stderr e exit code com o interpretador.
- Erro de compilação explícito (exit 65) para o que o backend ainda não representa
  (`Float`, `String`, variáveis, funções, classes) — nunca lowering silencioso.
- Erro de operando detectado pelo checker (`1 + true`, `-true`, `true // 2`) é rebaixado
  a `lox_panic`: o binário sai com 70 e a mesma mensagem do interpretador, inclusive
  depois de já ter impresso stdout (ADR-0031, decisão 9).
- Backend **L1**: `Float` desboxado (`double`), promoção `Int → Float`, `/` sempre `Float`,
  `%` de `Float`, comparações com semântica de `NaN` e `if`/`while`/blocos.
- Impressão de `Float` pela menor representação que faz round-trip, com as convenções do
  `repr` do Python, validada por fuzz contra `repr()` (400 bit patterns + especiais) e
  independente de locale (`lox_init` fixa `LC_NUMERIC=C`).
- Manifesto do corpus diferencial (`tests/corpus_manifest.py`) com os níveis `l0` e `l1`.
- 15 golden cases de `tests/cases` e 3 de `examples/` anotados (54 de 78 em `tests/cases`
  passam no `--check` agora; antes eram 39).
- Backend L2 (variáveis): `val`/`var` com `alloca` local e global para o topo, atribuição,
  escopo de bloco e sombreamento; o `for` C-style (desaçucarado pelo parser) já compila.
  O tipo do binding é o tipo do valor em runtime — `val f: Float = 2` guarda `Int`, como
  no interpretador (anotação não converte).
- Backend L2 (funções): declaração de topo, chamada direta, `return`, recursão e defaults
  resolvidos no call site; `Nil` vira `void`. Aridade errada e variável indefinida viram
  `lox_panic` com a mensagem do interpretador (stdout e exit code preservados).
- Backend L2b (açúcar): ternário, `and`/`or` e `??` com blocos + `phi`, curto-circuito
  preservado e dobra de literais (`false and x`, `true or x`); `for-in` fica para o L3/L6
  por depender de `Range`/`List`/`String`.
- Backend L3 (strings): `String` como `{byte_len, cp_len, data}` em globais constantes,
  concatenação (`lox_str_concat`), igualdade (`memcmp`), `len` em code points e `print`;
  arena de 64 MiB com panic determinístico.
- Backend L3 (interpolação): `"${expr}"` com `stringify` de `Int`/`Float`/`Bool`/`nil`/
  `String` (`lox_str_from_*`), `str()` e `repr()` com citação e escapes (`lox_str_quote`).

### Mudado

- **Release por workflow:** o `Release` agora é `workflow_dispatch` (inputs `version` e
  `dry_run`, default `true`): valida a versão contra `pyproject.toml`, builda/atesta e só
  então cria a tag `v<versão>` + GitHub Release e publica no PyPI. Tag `v*` manual não
  dispara mais release. O CodeQL passa a analisar também o runtime C (`c-cpp`, build
  manual) além do Python quando o repositório for público.

- **`exemplos/` virou `examples/`**: a pasta, os arquivos em português
  (`primos.lx`→`primes.lx`, `vendas.lx`→`sales.lx`) e os identificadores dos programas
  passaram para inglês; o README foi reescrito e as referências em testes, docs,
  `Makefile` e skills foram atualizadas. Os READMEs de `editors/` também estão em inglês.
- **`std.paths.join` virou `joinPath`**: `join` colidia com o builtin global
  `join(List[String], String)` e o módulo não passava em `--check` sozinho
  (`E3014 — Can't redefine builtin`). Atualize as chamadas para
  `paths.joinPath(base, child)`; o comportamento é o mesmo. Todos os módulos de `std/`
  agora passam em `--check` sem avisos.
- **Documentação da stdlib**: cabeçalhos de módulo em inglês e comentários `///`
  expandidos com contrato, casos de borda e determinismo; `docs/stdlib/` regenerado.
- **Licença dual MIT/Apache-2.0** ([ADR-0101](docs/adr/0101-licenca-dual-e-politica-de-contribuicao.md)):
  o projeto passa a ser distribuído sob `MIT OR Apache-2.0`, com `LICENSE-MIT`,
  `LICENSE-APACHE` e `NOTICE`; o metadado PEP 639 declara a expressão SPDX. Contribuições
  são inbound=outbound com DCO, sem CLA; `tests/official/` permanece MIT.
- **README público em inglês** ([ADR-0102](docs/adr/0102-ingles-na-vitrine-e-docs-pt-br.md)):
  a vitrine (README, CONTRIBUTING, SECURITY, CoC, templates, CI e commits) passa a ser
  em inglês; a spec, os ADRs e o roadmap seguem em pt-BR até a tradução da §14.2.
- **O nome é Loxia e a extensão é `.lx`** ([ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md)):
  "PyLox" era nome de trabalho desde o [ADR-0014](docs/adr/0014-identidade-e-invariantes.md).
  O pacote virou `loxia/`, o comando `loxia` (`python -m loxia`, `--version` →
  `loxia 1.0.0`), `main.py` mantém `from main import Loxia` e o alias `Lox`, e os fontes
  passaram de `.lox` para `.lx` (373 arquivos; `SOURCE_SUFFIX` no loader). O CLI não valida
  extensão, então scripts antigos continuam rodando; só `import` deixou de resolver `.lox`.
- **`RuntimeError` no lugar de `LoxRuntimeError`** ([ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md)):
  a classe embutida de erro de runtime perdeu a marca da linguagem — `except RuntimeError
  as e` substitui `except LoxRuntimeError as e` no tree-walk e no backend. A classe Python
  interna (`loxia_core/diagnostics/errors.py::LoxRuntimeError`) mantém o nome de herança do livro,
  e `Exception` continua a base.
- **Erros de compilação e de runtime mudaram de formato**
  ([ADR-0075](docs/adr/0075-diagnosticos-estruturados.md)): `[line N] Error at 'x': …`
  virou `arquivo:linha:col: error[CODIGO]: …` (+ trecho com caret na compilação). O
  binário nativo reproduz o mesmo cabeçalho no erro de runtime, com linha, coluna e
  código. Exit codes não mudaram (`65`/`70`/`66`/`2`). Quem parseava a linha antiga deve
  migrar para `--error-format=json` (`schema_version: 1`) ou `short`.
- **Contrato de memória** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)):
  GC Boehm, hard cap de 128 MiB e I1 até 64 MiB de memória viva; o ponto exato do
  `Out of memory.` deixa de ser determinístico, mas a mensagem e o exit code continuam.
- **`"..."` não aceita mais quebra de linha**: quem escrevia multilinha com `"` usa
  `"""..."""` (erro dirigido aponta a forma canônica). Ver
  [ADR-0070](docs/adr/0070-strings-multilinha-e-raw.md).
- **Promoção `Int → Float` só na aritmética** ([ADR-0059](docs/adr/0059-i4-check-limpo-compila.md)):
  `val x: Float = 2`, `x = 2`, `f(2)`, defaults e `return 2` em `-> Float` passaram a ser
  erro de tipo (Kotlin-like). Escreva `2.0` ou `2 as Float`. A aritmética não mudou
  (`1 + 2.0`, `4 / 2`, `1 == 1.0`).
- **`--check` e `--emit` deixam de divergir**: o furo `var x: Float = 1.5; x = 2`
  (check limpo, binário recusando) virou erro nos dois caminhos, com a mesma mensagem.


- `docs/spec/garantias.md`: I1 passa a valer para o corpus declarado e cobre stderr.
- `pyproject.toml`: extra `llvm` (`llvmlite>=0.50`); o interpretador continua sem
  dependências.

- **Catálogo de códigos gerado**: `docs/spec/erros.md` agora é gerado a partir de
  `Code`/`CODE_DESCRIPTIONS` (`make codes`, incluso em `make docs-sync`); o teste
  `test_catalogo_de_codigos_esta_atualizado` falha se a tabela defasar.

### Corrigido

- **Avisos de local não usado na stdlib**: `std.csv` e `std.json` capturavam
  `except RuntimeError as error` sem usar o binding; virou `_error`, eliminando o
  `W1001` ao checar os módulos.
- **stdin não-UTF-8 dependia do locale**: `io.readAll`/`io.readLine` agora leem bytes e
  decodificam UTF-8 estrito; no locale C o `surrogateescape` ecoava os bytes inválidos com
  exit 0. Os testes forçam `LC_ALL=C` e cobrem `readLine`.
- **Panic de primitiva sem posição** (`R2`): `substr`, `join`, `charCodeAt`,
  `fromCodePoint`, `os.exit` e `time.sleep` agora usam `R1000` com a mensagem e a
  posição do oráculo; `substr` também passou a rejeitar `end > len`. Teste diferencial
  com erro não capturado cobre os seis casos.
- **`io.write`/`io.writeErr` sem flush no binário** (`R1`, [ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md)):
  o oráculo flushava por chamada e o binário não, então `std.io.prompt` nunca mostrava a
  mensagem e qualquer consumidor de stdout em pipe (JSONL, MCP, LSP) travava. A comparação
  de bytes no fim do processo não pegava; o novo teste
  `test_io_write_flush_antes_de_bloquear_no_stdin` entrega o stdin só depois de ler a saída.
- **`return` dentro de `try`**: o frame de `try` é desempilhado em toda saída, o valor
  é avaliado antes do `finally`, o `finally` roda uma vez e funções locais/lambdas
  isolam os cleanups. `except ... as e` materializa `LoxRuntimeError` para que
  `e.message` não desreferencie NULL ([commit `c7666fb`]).
- **Igualdade de mapa**: o contador de profundidade não vaza mais em comparações com
  contagens diferentes; `charCodeAt(s, len(s))` vira erro em vez de ler o NUL.
- **`T?` na inferência genérica**: `T?` com `Int?` unifica `T = Int`, não `T = Int?`;
  `assertNotNil` deixa de gerar opcional aninhado no backend.
- **Chamada em contexto esperado publica tipo**: `return math.sqrt(x)` compila; `math.*`
  desembrulha `T?` estreitado antes da chamada nativa.
- **`Any as T` checa a tag no backend**: um `Any` com tipo errado agora vira `R1011`
  (`Can't cast value to T.`) como no tree-walk, em vez de reinterpretar o payload;
  `Int`/`Float` mantêm a promoção numérica. Regressão em `tests/test_backend.py`.
- **Exceções sintéticas com mensagem**: `Exception("x")`/`LoxRuntimeError("x")`
  constroem a instância com `message` (aridade 1), como no tree-walk.
- **Exceção de usuário não capturada**: o binário imprime `Tipo: mensagem`
  (`Unhandled exception: MyError: falhou`), igual ao `stringify` do interpretador.
- **`is`/`as` sobre `Any` agora são recursivos**: listas, mapas, tuplas e enums checam
  elementos, aridade e identidade (enum id / classe id), em vez de só a tag. Corrige
  `["a"] is List[Int]`, `(1, "a") is (Int, Int)`, `Size.Small is Color` e
  `Any as List[Int]`; o `is` de tupla estática com elementos `Any` também deixou de usar
  a comparação estática `same_as`.
- **`is`/`as` estático e opcional**: `5 is Int`, `5 is A` (false, em vez de panic),
  `T?` de escalar/classe/lista (`nil` → false, presente → checagem normal) e classe local
  passam pelo matcher; `T?` é boxeado como `{0,0}`/`{tag,payload}`.
- **Literais aninhados**: `val x: Any = [[1]]`/`{"a": {"b": 1}}` compilam (a checagem de
  tipo morta do literal foi removida; os elementos já eram boxeados).

## [1.0.0] — 2026-11-12

**1.0.0 é a versão de referência da linguagem no tree-walk.** Não há backend nativo
publicado; o LLVM L0–L2 é pós-1.0. A release é local (sem publicação externa).

### Adicionado

- Interpretador tree-walk completo dos caps. 4–13: scanner, parser, resolver, funções,
  closures, classes, `this`, `super` e herança.
- `val`/`var` com imutabilidade de binding, parâmetros imutáveis e `var` explícito.
- `fn`, `elif`, `;` opcional, ternário, `??`, `?.`, interpolação e escapes.
- `Int`/`Float` separados, promoção só `Int → Float`, `//`, `%`, `**` e bits i64.
- Ranges, `for-in`, `List[T]` e `Map[K, V]`.
- Defaults, campos declarados, lambdas e tipos de função.
- Checker gradual `--check`: anotações, inferência local, `T?`, uniões, `is T` e narrowing.
- Generics T3b: funções `fn id[T]`, inferência na chamada, sem constraints.
- Conversões D-8: `as` explícito, `Int.parse`/`Float.parse` → `T?` e `math.*`
  determinístico.
- `--debug` com checagem de overflow de `Int`; release continua wrapping.

### Mudado

- Freeze da 1.0: erro de runtime fatal (exit 70), sem `try`/`Result`.
- `clock` removido do prelúdio; prelúdio determinístico (`len`, `str`, `repr`, `range`,
  `Int`, `Float`, `math`).
- Strings UTF-8 com `len` em code points; identificadores ASCII.
- `print` continua statement; single-file.
- `Any` permanece na linguagem, mas o backend L0–L2 o rejeita.

### Fora da 1.0

Backend LLVM, tuplas, classes/métodos genéricos, constraints/traits, módulos/stdlib,
contratos/JSON, `Result`/`try`, variádicos, trailing closure, `match`/enums, diagnósticos
com spans/caret e transcendentais de `math`. Ver [`docs/roadmap.md`](docs/roadmap.md) e
[ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md).

### Verificação

- `make check` verde: **678 passed + 8 xfailed**, ruff e mypy strict limpos.
- Suíte oficial adaptada: 112 pass + 8 `xfail` intencionais.
- Benchmarks dentro do limite de regressão do baseline.
- `uv run main.py --version` → `pylox 1.0.0`.
