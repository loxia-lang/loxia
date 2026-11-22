---
name: lox-commits
description: Formato de commit e PR na Loxia — Conventional Commits, DCO, escopos, títulos de PR e divisão do trabalho em commits.
whenToUse: Ao criar, emendar ou revisar um commit ou título de PR; ao decidir em quantos commits dividir uma mudança.
---

# Conventional commits (Loxia)

Use this skill whenever you create, amend or review a commit or a pull request title.
The rules are also in [`CONTRIBUTING.md`](../../../CONTRIBUTING.md); this file is the
agent-facing checklist.

## Language

**Everything that reaches Git is English**: commit headers, bodies and footers (including
`Signed-off-by`), branch names, PR titles, PR descriptions, review comments, issue comments,
tag names and release notes. Portuguese belongs in local conversations and non-Git docs;
never in a commit, PR or review thread. This applies even when the user writes in
Portuguese.

## Format

```
<type>(<scope>)!: <subject>

<body>

<footer>
```

- `<type>` is lowercase and must be one of: `feat`, `fix`, `docs`, `style`, `refactor`,
  `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- `<scope>` is optional, lowercase and kebab-case. Prefer one of: `frontend`, `semantics`,
  `execution`, `backend`, `runtime`, `stdlib`, `cli`, `lsp`, `fmt`, `editors`, `docs`,
  `adr`, `ci`, `deps`, `tests`, `bench`, `release`, `license`, `community`, `tooling`.
- `!` marks a breaking change; add a `BREAKING CHANGE:` footer explaining the migration.
- `<subject>` is English, imperative, no trailing period, and the header stays under 100
  characters.
- The body explains **why**, not what the diff already says. Reference ADRs and issues.

## Examples

```
feat(backend): lower enum payloads for L6
fix(checker): narrow T? after an early return
docs(adr): record the dual license
chore(deps): bump llvmlite to 0.51
feat(cli)!: rename --json to --json-lines
```

## Sign-off

Every commit needs the DCO trailer:

```bash
git commit -s -m "fix(io): decode stdin as strict UTF-8"
```

The trailer is `Signed-off-by: Name <email>` in the body. Dependabot and GitHub Actions
commits are exempt. A PR without sign-off on its commits fails the DCO check.

## PR titles and merge strategy

Feature/fix PRs target `dev` and are **squash-merged**; the **PR title becomes the squash
commit**. Write the title exactly like a commit header. The CI check validates it, so a
good local commit does not save a bad PR title.

Release PRs go `dev` → `main` with a **merge commit**, not squash. Never delete `dev` when
merging it. See [`lox-git-flow`](../lox-git-flow/SKILL.md) for the branch model.

## Splitting work

- One logical change per commit/PR. Do not mix formatting, refactors and behavior.
- A bug fix includes its regression test in the same commit.
- A behavior change updates `docs/spec/` in the same commit.
- A design decision adds an ADR and updates `docs/adr/README.md` and `docs/decisoes.md`.
- Generated files are regenerated (`make docs-sync`, `make grammar`, `make primitives`),
  never hand-edited.

## Before committing

```bash
make check-fast                         # lint + format + mypy + tests + docs
uv run python tools/check_commit_msg.py .git/COMMIT_EDITMSG
uv run python tools/check_pr_title.py "feat(cli): add a flag"
```

Never commit `NOTAS.local.md`, `__pycache__`, `.venv`, caches, `dist/` or secrets. Do not
force-push `main` or `dev`, rewrite published history or bypass the syntax/feature gates in
[`docs/adr/0014`](../../../docs/adr/0014-identidade-e-invariantes.md) and
[`docs/adr/0066`](../../../docs/adr/0066-orcamento-e-gate-sintatico.md).

## Changelog

`feat` normally belongs under **Added**, `fix` under **Fixed**, `perf`/breaking changes
under **Changed**. `docs`, `test`, `ci`, `chore` and `style` are usually omitted. The
release notes are curated from the changelog, not generated from raw commit subjects.
