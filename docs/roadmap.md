# Roadmap

Esta é a página para responder **"o que vem agora?"**. O detalhe executável vive nas
issues; ideias em [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas);
decisões adiadas no [ADR-0107](adr/0107-adiados-e-nao-objetivos.md). Este arquivo é
narrativa, não status: a fonte de status é a issue (aberta/fechada e milestone).

## Onde estamos (2026-11-18)

- Repositório público; **1.1.0** lançada (PyPI + GitHub Release).
- Linguagem 1.0 congelada; backend **L0–L6 + T7** fechado; **M8** (performance) fechado.
- **M9** (ecossistema) em andamento: MCP, cliente de editor e distribuição.
- **Site no ar**: <https://loxia-lang.github.io/loxia/> ([#4](https://github.com/loxia-lang/loxia/issues/4)).
- **LSP sem as lacunas P1**: completion herdada, signature importado/herdado, `inlayHint` e
  rename cross-file semântico ([#7](https://github.com/loxia-lang/loxia/issues/7)).

## Agora (Now)

1. **M9 — editor**: publicar o cliente VS Code e o asset de grammar ([#5](https://github.com/loxia-lang/loxia/issues/5)).
2. **M9 — MCP**: servidor `loxia-mcp` fino sobre o CLI ([#6](https://github.com/loxia-lang/loxia/issues/6)).
3. **Decisões abertas**: `fs.open` ([#16](https://github.com/loxia-lang/loxia/issues/16)) e gerador de AST ([#15](https://github.com/loxia-lang/loxia/issues/15)). Contratos foram decididos como biblioteca ([ADR-0108](adr/0108-contratos-como-biblioteca.md)) e a sintaxe ficou adiada com gatilhos.

## Próximo (Next)

- `std/lsp` framing em Lox puro ([#9](https://github.com/loxia-lang/loxia/issues/9)).
- Piloto de `std.contracts` em módulos da stdlib/exemplos e property tests ([ADR-0108](adr/0108-contratos-como-biblioteca.md)).
- `loxia add`/`remove` depois de um writer de TOML ([#8](https://github.com/loxia-lang/loxia/issues/8), bloqueada).
- Corpus de conformidade como artefato `lox-core` ([#10](https://github.com/loxia-lang/loxia/issues/10)).
- Lacunas do runner de testes: `--json`, cobertura e localização de falha ([#11](https://github.com/loxia-lang/loxia/issues/11)).
- Primeiro programa real + tutorial/cookbook ([#12](https://github.com/loxia-lang/loxia/issues/12)).
- Suíte pública de benchmarks ([#13](https://github.com/loxia-lang/loxia/issues/13)).

## Depois (Later)

- Self-hosting do `loxia fmt` (começar pelo formatter), depois do `fs.open`.
- `REPL :type`, gerador de release notes em Loxia, tree-sitter e snapshot de AST.
- `net`, registry de pacotes e bindgen TOML: só com o gatilho da thread de Ideas.
- Playground WASM, debugger DAP e hot reload: ideias em Discussions.
- `if`/bloco como expressão, exceções recuperáveis, constraints em classes e unificação
  mutável: abertas, sem issue até doer.

## Decidido não agora

Sintaxe de contratos (`requires`/`ensures`/`invariant`; ADR-0108), generics além do MVP, operator overloading, trailing closure, `match` estrutural,
extension methods, metaclasses/decorators, math transcendentais e paralelismo. Gatilhos em
[ADR-0107](adr/0107-adiados-e-nao-objetivos.md); para contratos, [ADR-0108](adr/0108-contratos-como-biblioteca.md).

## Regras

- **Issue** = trabalho com critério de pronto e ciclo de vida; fecha no PR.
- **Discussion › Ideas** = ideia sem compromisso; vira issue só quando o gatilho dispara.
- **ADR** = decisão tomada, inclusive "não agora".
- Board/kanban é **view**, nunca fonte; labels `P0–P3`, `area:*`, `size:*`.
- Se não vai ser feito nas próximas ~6 semanas, não é issue: é Next/Later ou Ideas.
