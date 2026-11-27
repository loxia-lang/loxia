# Roadmap

Esta é a página para responder **"o que vem agora?"**. O detalhe executável vive nas
issues; ideias em [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas);
decisões adiadas no [ADR-0107](adr/0107-adiados-e-nao-objetivos.md) (linguagem/runtime)
ou no ADR próprio (processo/release). Este arquivo é
narrativa, não status: a fonte de status é a issue (aberta/fechada e milestone).

## Onde estamos (2026-11-27)

- Repositório público; **1.3.0** é a release atual (no PyPI desde 2026-11-27); **1.2.0** foi
  a primeira com o servidor MCP e **1.1.0** a primeira release pública.
- A linguagem está na 1.x, com o backend **L0–L6 + T7** fechado e o runtime C como produto.
  A 1.3.0 entregou o ponto de entrada `main -> Result`
  ([ADR-0148](adr/0148-ponto-de-entrada-main-result.md)), valores de função com assinatura
  em runtime ([ADR-0147](adr/0147-valores-de-funcao-assinatura-runtime.md)),
  `break`/`continue`, `match` de literais, `Bytes`/`regex`, o objeto de classe fora do tipo
  função ([ADR-0150](adr/0150-objeto-de-classe-nao-e-valor-de-funcao.md)) e o formatter 2.0.
  Foi também a leva mais pesada de entradas de quebra; a próxima major é a **2.0**.
- **Motores**: o [ADR-0149](adr/0149-motores-primarios-thir-e-congelamento.md) mudou o eixo
  do projeto — o nativo vira o produto e o `run` compila com cache. A **F0** foi entregue
  ([#244](https://github.com/loxia-lang/loxia/issues/244),
  [ADR-0152](adr/0152-run-aot-aceitacao-flags-e-cache.md)): `run` compila, `--interpret` é o
  oráculo, o cache tem limite e `loxia cache prune`. A F1 (IR de controle) está aberta.
- **Editor/LSP**: as lacunas P1 e o [#46](https://github.com/loxia-lang/loxia/issues/46)
  estão fechados; o build frio do workspace deixou de rodar checker e o recheck por edição
  coalesce ([ADR-0143](adr/0143-lsp-didchange-coalescing-e-reuso.md),
  [ADR-0151](adr/0151-cache-de-analise-por-arquivo-no-lsp.md)). O cliente VS Code 1.1.0
  está pronto em [`loxia-lang/loxia-vscode`](https://github.com/loxia-lang/loxia-vscode);
  falta o publisher/namespace e a publicação no Marketplace/Open VSX.
- **MCP**: `loxia mcp`/`loxia-mcp` segue empacotado desde a 1.2.0, com `server.json`; a 1.3.0
  acrescentou `loxia_format` com `TextEdit[]` exatos e o catálogo de códigos no índice
  ([ADR-0112](adr/0112-mcp-servidor-stdio.md), [ADR-0137](adr/0137-mcp-format.md)).
- **Site no ar**: <https://loxia-lang.github.io/loxia/>
  ([#4](https://github.com/loxia-lang/loxia/issues/4)).

## Programa de motores (ADR-0149)

Decisão de 2026-11-26: o **nativo vira o produto**. `loxia run` compila com cache
content-addressed (fonte + deps + identidade do compilador + flags + plataforma + heap) e o
tree-walk fica como REPL, `--interpret` e oráculo. O **THIR** (árvore tipada e desugarada)
passa a ser o eixo entre o checker e os motores; a **IR de controle** (blocos/phi/cleanup)
fica interna ao backend, honrando o [ADR-0065](adr/0065-hir-lite-controle.md); o Python
congela **por módulo** — interpretador → lowering → front → checker — em portões de
paridade e soak; o oráculo migra para spec + corpus + golden; e o self-host tem três níveis
(self-executing, self-hosted, reprodutível).

Fases, portões G1–G5, indicadores, riscos e o painel vivem em
[`plano-de-motores.md`](plano-de-motores.md) — esta página não os duplica. Regra do
programa: a fase seguinte vira issue quando o portão anterior fecha; o status real está na
issue.

## Agora (Now)

1. **F0 — `run` AOT com cache** ([#244](https://github.com/loxia-lang/loxia/issues/244)):
   **entregue em 2026-11-27** ([ADR-0152](adr/0152-run-aot-aceitacao-flags-e-cache.md)):
   `run prog.lx` compila e executa o binário, `--interpret` mantém o tree-walk, o REPL segue
   interpretado e o cache não muda bytes. A medição cold/warm vive no
   [`plano-de-motores.md`](plano-de-motores.md).
2. **F1 — IR de controle** ([#245](https://github.com/loxia-lang/loxia/issues/245)): blocos,
   terminadores, phi e pilha de cleanup internos ao backend, migrando exceções/`match`/
   classes e honrando o gatilho do [ADR-0065](adr/0065-hir-lite-controle.md) (o lowering de
   exceções e enums já passou do orçamento de ~350 linhas). Sem mudança de ABI nem de
   bytes; a F2 (THIR) abre no fim desta.
3. **Publicar o cliente VS Code 1.1.0**: criar o publisher `loxia-lang` no Marketplace e o
   namespace no Open VSX, configurar `VSCE_PAT`/`OVSX_PAT` e taguear no repo
   [`loxia-vscode`](https://github.com/loxia-lang/loxia-vscode). É o último item do
   ecossistema que não depende de código novo.

## Próximo (Next)

- **F2 — THIR + serialização** (issue abre no fim da F1): árvore tipada e desugarada com
  binding em slots/células, IDs estáveis, desugaring explícito e spans preservados; o
  lowering passa a consumi-la e as side tables por identidade de nó somem. O snapshot do
  THIR vira contrato de revisão, como o do front
  ([ADR-0129](adr/0129-oraculo-do-front-end.md)).
- **Piloto de `std.contracts`** em módulos da stdlib/exemplos e property tests
  ([ADR-0108](adr/0108-contratos-como-biblioteca.md)) — em andamento em
  `std.paths`/`std.convert`; `std.numeric`/`std.lists` ficaram só com property tests após o
  benchmark.
- **Primeiro programa real + tutorial/cookbook**
  ([#12](https://github.com/loxia-lang/loxia/issues/12)): um programa que roda no wheel, um
  tutorial de 30 minutos e uma página "por que Loxia" ancorada nele.
- **Corte da 2.0**: decidir escopo e janela da próxima major — ela já herda as quebras da
  1.3.0 (formatter 2.0, AST JSON v2, remoção do `for` C-style, objeto de classe fora do tipo
  função) e a **mudança do `run` padrão** (a F0 já a implementou; `--interpret` é a migração;
  a entrada está em "Mudado (quebra)" no CHANGELOG).

## Depois (Later)

- **F3–F6**: THIR eval em Loxia, compilador Loxia, front Loxia com ponte AST JSON e checker
  Loxia, cada uma com os seus portões. O self-host do `loxia fmt`
  ([ADR-0124](adr/0124-fmt-self-host-e-pacotes-por-repo.md)) anda junto do front.
- Corpus de conformidade como artefato `lox-core`
  ([#10](https://github.com/loxia-lang/loxia/issues/10)): adiado até existir spec `lox-core`
  publicada e implementação externa pedindo
  ([ADR-0115](adr/0115-corpus-de-conformidade-adiado.md)).
- Suíte pública de benchmarks ([#13](https://github.com/loxia-lang/loxia/issues/13)): adiada
  até um release em que performance faça parte da mensagem e existir protocolo reprodutível
  + consumidor ([ADR-0116](adr/0116-benchmarks-publicos-adiados.md)).
- **Runner**: worker pool/cache nativo, se a suíte crescer.
- `std.toml` (dados, paridade com `tomllib`): promoção só com consumidor real
  ([ADR-0118](adr/0118-toml-na-toolchain-e-edicao-de-manifest.md)).
- `REPL :type`, gerador de release notes em Loxia, tree-sitter e snapshot de AST.
- `net`, registry de pacotes e bindgen TOML: só com o gatilho da thread de Ideas.
- Playground WASM, debugger DAP e hot reload: ideias em Discussions.
- `if`/bloco como expressão, exceções recuperáveis, constraints em classes e unificação
  mutável: abertas, sem issue até doer.

## Decidido não agora

Sintaxe de contratos (`requires`/`ensures`/`invariant`; ADR-0108), generics além do MVP, operator overloading, trailing closure, `match` estrutural,
extension methods, metaclasses/decorators, math transcendentais e paralelismo. Gatilhos em
[ADR-0107](adr/0107-adiados-e-nao-objetivos.md); para contratos, [ADR-0108](adr/0108-contratos-como-biblioteca.md).
**VM de bytecode**: adiada — só entra se o REPL virar primeira classe ou a medição exigir, e
nunca junto com o THIR eval ([ADR-0149](adr/0149-motores-primarios-thir-e-congelamento.md) §4).
Gerador de AST/visitor: mantido manual com cobertura de protocolo ([ADR-0117](adr/0117-ast-manual-e-cobertura-de-visitantes.md)); reabre com 3+ nós por ciclo ou um 5º visitante.

## Regras

- **Issue** = trabalho com critério de pronto e ciclo de vida; fecha no PR.
- **Discussion › Ideas** = ideia sem compromisso; vira issue só quando o gatilho dispara.
- **ADR** = decisão tomada, inclusive "não agora".
- Board/kanban é **view**, nunca fonte; labels `P0–P3`, `area:*`, `size:*`.
- Se não vai ser feito nas próximas ~6 semanas, não é issue: é Next/Later ou Ideas.
