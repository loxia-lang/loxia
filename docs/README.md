# Language documentation

Portal to the technical and syntax documentation and to the design decisions.

> **Language:** the public showcase (README, CONTRIBUTING, SECURITY, Code of Conduct,
> templates, CI and commits) is in English. The specification and the technical docs are
> now in English; the 1.0 archive and the existing ADRs remain in Portuguese
> ([ADR-0102](adr/0102-ingles-na-vitrine-e-docs-pt-br.md)).

> **Status:** the specification describes the interpreter **as it exists today** (the Lox
> from Part II of the book + `fn`, `elif`, optional `;`, `val`/`var`, `?.`/`??`, ternary,
> escapes, `List[T]` lists, the hybrid `len`/`str`/`repr` API + methods and the `--check`
> checker). What is still a plan lives in [`roadmap.md`](roadmap.md),
> [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas),
> [`../TIPOS.md`](../TIPOS.md) and [ADR-0107](adr/0107-adiados-e-nao-objetivos.md), and
> does **not** apply to the current code.

## Sources of truth

| Question | Where |
| --- | --- |
| What does the language do today? | [`spec/`](spec/) — lexicon, syntax, semantics, errors |
| How does it work inside? | [`tech/arquitetura.md`](tech/arquitetura.md) |
| Why did we decide X? | [`adr/`](adr/) — Architecture Decision Records |
| Which decisions have already been made? | [`decisoes.md`](decisoes.md) — executive summary + links |
| What comes after 1.0? | [`roadmap.md`](roadmap.md) |
| What is still open? | [issues labeled `decision`](https://github.com/loxia-lang/loxia/issues?q=label%3Adecision) |
| What do we want to do later? | [`roadmap.md`](roadmap.md) and [ADR-0107](adr/0107-adiados-e-nao-objetivos.md) |
| What is just an idea? | [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas) |
| Pending type issues | [`../TIPOS.md`](../TIPOS.md) |
| Rules for agents/devs | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) and `.dsh/skills/` |

Maintenance rule: **behavior changed → `spec/` changes in the same commit**. A decision that
is hard to reverse → a new ADR. Discussion still open → a `decision` issue or Discussions ›
Ideas, not `spec/`.

## Specification

1. [Lexicon](spec/lexico.md) — files, comments, tokens, literals, keywords.
2. [Syntax](spec/sintaxe.md) — EBNF grammar, precedence, `for` desugaring.
3. [Semantics](spec/semantica.md) — values, scopes, functions, classes, inheritance, errors.
4. [Errors](spec/erros.md) — messages, phases, exit codes.

## Technical

- [Architecture](tech/arquitetura.md) — pipeline, modules, visitor, environments, resolver.
- [Documentation index](tech/docs-index.md) — generated `loxia/_spec/index.json` and `llms.txt` for agents/site (ADR-0111).

## Design

- [Decisions already made](decisoes.md) — executive summary; the source of truth is the ADRs.
- [ADRs](adr/README.md) — process, template and index.
  - [ADR-0001](adr/0001-registrar-decisoes-em-adrs.md) — recording decisions in ADRs.
  - [ADR-0002](adr/0002-tree-walk-como-oraculo.md) — the tree-walk is the executable specification.
  - [ADR-0003](adr/0003-diagnosticos-por-execucao.md) — per-run diagnostics.
  - [ADR-0004](adr/0004-identidade-dos-nos-de-ast.md) — AST nodes have identity.
  - [ADR-0005](adr/0005-val-var-imutabilidade.md) — `val`/`var` and immutability.
  - [ADR-0015](adr/0015-listas-tipadas.md) — `List[T]` lists.
  - [ADR-0016](adr/0016-api-stdlib-hibrida.md) — hybrid stdlib API.
- [Glossary](glossario.md)
