# Roadmap

Esta é a página para responder **"o que vem agora?"**. O detalhe executável vive nas
issues; ideias em [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas);
decisões adiadas no [ADR-0107](adr/0107-adiados-e-nao-objetivos.md) (linguagem/runtime)
ou no ADR próprio (processo/release). Este arquivo é
narrativa, não status: a fonte de status é a issue (aberta/fechada e milestone).

## Onde estamos (2026-11-20)

- Repositório público; **1.2.0** é a release atual (MCP, PyPI + GitHub Release);
  **1.1.0** foi a primeira release pública.
- Linguagem 1.0 congelada; backend **L0–L6 + T7** fechado; **M8** (performance) fechado.
- **M9** (ecossistema) em andamento: MCP, cliente de editor e distribuição. O cliente
  VS Code já vive em `loxia-lang/loxia-vscode` (ADR-0109) e a grammar é asset de release;
  falta criar publisher/namespace e publicar a 1.1.0. O servidor MCP foi implementado
  (`loxia mcp`/`loxia-mcp`, ADR-0112), validado no MCP Inspector e empacotado para a
  **1.2.0** com `server.json`; a publicação no PyPI e no MCP Registry é o passo manual
  do release.
- **Site no ar**: <https://loxia-lang.github.io/loxia/> ([#4](https://github.com/loxia-lang/loxia/issues/4)).
- **LSP sem as lacunas P1**: completion herdada, signature importado/herdado, `inlayHint` e
  rename cross-file semântico ([#7](https://github.com/loxia-lang/loxia/issues/7)).
- **Dependências sem atrito**: `loxia add`/`remove` editam `loxia.toml` com editor escopado
  (comentários, ordem e CRLF preservados; `C0004` em vez de reescrita) e `--dry-run` mostra
  o diff ([#8](https://github.com/loxia-lang/loxia/issues/8), [ADR-0118](adr/0118-toml-na-toolchain-e-edicao-de-manifest.md)).
- **Protocolo stdio em Lox puro**: `std.jsonrpc`, `std.framing` e `std.documents`, com
  `std.json.parseResult`, harness de transcrição e diferencial nos dois motores
  ([#9](https://github.com/loxia-lang/loxia/issues/9), [ADR-0113](adr/0113-protocolo-stdio-jsonrpc-framing-documents.md)).
  O servidor LSP continua Python; `std/lsp` só nasce com política de servidor.

## Agora (Now)

1. **M9 — editor**: publicar a 1.1.0 do cliente VS Code no Marketplace/Open VSX e
   confirmar o asset de grammar no release ([#5](https://github.com/loxia-lang/loxia/issues/5));
   o split, os testes, o CI e o empacotamento já estão implementados.
2. **M9 — MCP**: servidor `loxia-mcp` fino sobre o CLI ([#6](https://github.com/loxia-lang/loxia/issues/6)).
   **Implementado e validado no Inspector** (ADR-0112: modern-only 2026-07-28, zero-dep,
   `--sandbox`); a release 1.2.0 leva o pacote e o `server.json`; a publicação no PyPI e
   no MCP Registry é o passo manual do release, seguida de validação com os demais
   clientes-alvo.
3. **Decisões abertas**: contratos foram decididos como biblioteca ([ADR-0108](adr/0108-contratos-como-biblioteca.md)) e a sintaxe ficou adiada com gatilhos; o gerador de AST foi decidido como manual + guard ([ADR-0117](adr/0117-ast-manual-e-cobertura-de-visitantes.md)). `fs.open` foi entregue com handles ([#16](https://github.com/loxia-lang/loxia/issues/16), [ADR-0119](adr/0119-fs-open-handles-e-erro-de-host.md)).

## Próximo (Next)

- LSP: fechar as lacunas do [#46](https://github.com/loxia-lang/loxia/issues/46) — references/
  highlight, `typeDefinition`/`implementation`, tags de não usado, fix-all, AST recuperada
  para tooling, buffers não salvos nos imports, rename de arquivo e hierarquia de tipos
  (fases 1–4; inspirado no pyrefly, sem herdar código Rust).
- Piloto de `std.contracts` em módulos da stdlib/exemplos e property tests ([ADR-0108](adr/0108-contratos-como-biblioteca.md)) — **em andamento** em `std.paths`/`std.convert`; `std.numeric`/`std.lists` ficaram só com property tests após o benchmark de performance.
- Spike de `std.toml` (dados, paridade com `tomllib`): [ADR-0118](adr/0118-toml-na-toolchain-e-edicao-de-manifest.md) separou dados de edição; promoção só com consumidor real ([#53](https://github.com/loxia-lang/loxia/issues/53)).
- ~~Lacunas do runner de testes: `--json`, cobertura e localização de falha
  ([#11](https://github.com/loxia-lang/loxia/issues/11)).~~ **Fechado**: protocolo v2,
  envelope JSON v1, `e.site` ([ADR-0120](adr/0120-localizacao-de-falha-em-excecoes.md)) e
  matriz de features ([ADR-0121](adr/0121-matriz-de-cobertura-de-features.md)); próximo é
  worker pool/cache nativo, se a suíte crescer.
- Primeiro programa real + tutorial/cookbook ([#12](https://github.com/loxia-lang/loxia/issues/12)).

## Depois (Later)

- Self-hosting do `loxia fmt` (começar pelo formatter); `fs.open` já está disponível ([ADR-0119](adr/0119-fs-open-handles-e-erro-de-host.md)).
- Corpus de conformidade como artefato `lox-core` ([#10](https://github.com/loxia-lang/loxia/issues/10)):
  adiado até existir spec `lox-core` publicada e implementação externa pedindo
  ([ADR-0115](adr/0115-corpus-de-conformidade-adiado.md)).
- Suíte pública de benchmarks ([#13](https://github.com/loxia-lang/loxia/issues/13)):
  adiada até um release em que performance faça parte da mensagem e existir protocolo
  reprodutível + consumidor ([ADR-0116](adr/0116-benchmarks-publicos-adiados.md)).
- `REPL :type`, gerador de release notes em Loxia, tree-sitter e snapshot de AST.
- `net`, registry de pacotes e bindgen TOML: só com o gatilho da thread de Ideas.
- Playground WASM, debugger DAP e hot reload: ideias em Discussions.
- `if`/bloco como expressão, exceções recuperáveis, constraints em classes e unificação
  mutável: abertas, sem issue até doer.

## Decidido não agora

Sintaxe de contratos (`requires`/`ensures`/`invariant`; ADR-0108), generics além do MVP, operator overloading, trailing closure, `match` estrutural,
extension methods, metaclasses/decorators, math transcendentais e paralelismo. Gatilhos em
[ADR-0107](adr/0107-adiados-e-nao-objetivos.md); para contratos, [ADR-0108](adr/0108-contratos-como-biblioteca.md).
Gerador de AST/visitor: mantido manual com cobertura de protocolo ([ADR-0117](adr/0117-ast-manual-e-cobertura-de-visitantes.md)); reabre com 3+ nós por ciclo ou um 5º visitante.

## Regras

- **Issue** = trabalho com critério de pronto e ciclo de vida; fecha no PR.
- **Discussion › Ideas** = ideia sem compromisso; vira issue só quando o gatilho dispara.
- **ADR** = decisão tomada, inclusive "não agora".
- Board/kanban é **view**, nunca fonte; labels `P0–P3`, `area:*`, `size:*`.
- Se não vai ser feito nas próximas ~6 semanas, não é issue: é Next/Later ou Ideas.
