# Contributing to Loxia

Thanks for taking the time to read this. Loxia is a small language with a deliberately
small surface: a tree-walk interpreter that is the executable specification, an optional
LLVM backend, and a standard library built on a native kernel. Contributions are welcome
in code, tests, documentation, diagnostics and tooling.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License and sign-off

Loxia is dual-licensed under **MIT OR Apache-2.0**. Contributions are
**inbound = outbound**: unless you state otherwise, anything you submit is licensed under
the same two licenses, with no additional terms. See
[ADR-0101](docs/adr/0101-licenca-dual-e-politica-de-contribuicao.md).

Every commit must carry the Developer Certificate of Origin 1.1 sign-off:

```bash
git commit -s -m "fix(checker): narrow optional after early return"
```

The sign-off is a `Signed-off-by: Name <email>` trailer that certifies you wrote the
change or have the right to submit it. Do not add a sign-off for someone else. There is no
CLA.

## Before you start

- **Bug?** Open a bug report with a minimal `.lx` program, the version (`loxia --version`),
  the command you ran, and the expected/actual output. A failing golden case is the best
  report.
- **Feature or syntax change?** Open an issue first. The project has an admission gate for
  semantics ([ADR-0014](docs/adr/0014-identidade-e-invariantes.md)) and a stricter gate for
  syntax ([ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md)): new syntax needs human
  approval, a real pain point, one canonical spelling, and a test that polices it. The agent
  is not allowed to expand the grammar on its own.
- **Large refactor?** Discuss it before writing code. A small, focused diff is easier to
  review and to revert.

The roadmap lives in [docs/roadmap.md](docs/roadmap.md). Read the **Now** section before
proposing something that is already queued or explicitly out of scope. Ideas go to
[Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas);
deferred decisions are in [ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md).

## Development setup

Requirements: Python 3.13 and [`uv`](https://docs.astral.sh/uv/). The native backend is
optional and needs `llvmlite`, a C compiler and the Boehm GC development headers
(`libgc-dev` on Debian/Ubuntu, `bdw-gc` on Homebrew).

```bash
git clone https://github.com/loxia-lang/loxia.git
cd loxia
uv sync --all-groups --extra llvm
uv run loxia --version
```

Run from the repository root; that is the supported layout. `.venv/`, caches and
`AGENTS.md` are not versioned.

## Checks

```bash
make check-fast     # ruff + format + mypy + pytest (no native builds) + docs freshness
make check          # everything, including the native backend suite
make test-fast      # pytest without backend builds
make bench          # performance vs bench/baseline.json (run when touching hot paths)
```

`make check-fast` is the loop while iterating. `make check` is the gate before opening a
PR. If the backend is not installed, the backend tests are skipped locally; CI always runs
them with `libgc` and fails if `llvmlite` is missing.

The golden cases live in `tests/cases/*.lx` and are self-explanatory:

```lox
print(1 + 2)  # expect: 3
```

Use `# expect runtime error: MSG` for exit 70 and `# expect error: MSG` for exit 65. The
official Crafting Interpreters suite in `tests/official/` is a separate regression net; do
not edit its cases to make a test pass.

## Commit messages

The project uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
All Git-facing text is in English: commit messages, branch names, PR titles and
descriptions, review comments, tags and release notes. Messages are imperative and describe
**why** the change exists.

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`,
`revert`.

Useful scopes: `frontend`, `semantics`, `execution`, `backend`, `runtime`, `stdlib`, `cli`,
`lsp`, `fmt`, `editors`, `docs`, `adr`, `ci`, `deps`, `tests`, `bench`, `release`. The scope
is optional; use it when it makes the subject clearer.

Examples:

```
feat(backend): lower enum payloads for L6
fix(checker): narrow T? after an early return
docs(adr): record the dual license
chore(deps): bump llvmlite to 0.51
```

A breaking change uses `!` after the type/scope and a `BREAKING CHANGE:` footer. Explain
the migration and update the relevant ADR and `docs/spec/` in the same PR.

Feature PRs are squash-merged into `dev`; the PR title becomes the squash commit, so it must
follow the same convention. The CI check rejects titles that do not. Release PRs from
`dev` to `main` use a merge commit. DCO sign-off is checked on the commits in the PR;
configure your client with `git commit -s` (or add the trailer when editing the commit
message).

## Branches

| Branch | Role | Rules |
| --- | --- | --- |
| `main` | release, default | protected: no deletion/force-push, PR required, `CI success` |
| `dev` | long-lived integration | protected: no deletion/force-push, PR required, `CI success` |
| `feat/*`, `fix/*`, `docs/*`, `test/*`, `chore/*` | work | branched from `dev`, deleted after merge |

- Every feature/fix starts from `dev` and lands in `dev` by pull request. Do not commit
  directly to `main` or `dev`.
- `dev` is permanent: never merge it with `--delete-branch`. Automatic branch deletion is
  disabled in the repository; delete only the feature branch after its PR merges.
- A release is a PR from `dev` to `main` (merge commit), followed by a tag from `main`.
  Issues close in the feature PR, not in the release PR.
- Exceptional hotfixes branch from `main`, merge into `main`, and are synced back into
  `dev`.
- The full procedure is in the [`lox-git-flow`](.dsh/skills/lox-git-flow/SKILL.md) skill.

## Pull requests

- One logical change per PR. Do not mix formatting, refactors and behavior changes.
- Add or update tests in the same PR. A bug fix needs a regression case.
- If the observable behavior changed, update `docs/spec/` in the same PR.
- If the change is a design decision, add an ADR under `docs/adr/`, update
  `docs/adr/README.md` and `docs/decisoes.md`, and link it from the PR.
- Regenerate generated artifacts instead of editing them by hand: `make docs-sync`,
  `make grammar`, `make primitives`, `make codes`.
- Do not commit `AGENTS.md`, `__pycache__`, `.venv`, caches or `dist/`.
- Keep the PR description short: what changed, why, how it was tested, and what is out of
  scope.
- Use `Closes #N` when the PR resolves an issue.

## Code style

- Python 3.13, no runtime dependencies. New dependencies require a discussion and an ADR
  when they affect the product.
- Imports are absolute (`from loxia_core...`), and dependency direction is
  `frontend ← semantics ← execution` with `diagnostics` as a leaf.
- Types are mandatory; `mypy` runs in strict mode. `ruff check` and `ruff format --check`
  are gates.
- Language values are dynamic `object` plus `assert isinstance(...)`; use
  `loxia_core.execution.numeric` helpers instead of `isinstance(x, (int, float))`.
- Runtime error messages are English. Public docs are English; the specification and ADRs
  are currently Portuguese (see [docs/README.md](docs/README.md)).
- Do not add debug `print()` calls to `loxia_core/`.
- Keep diffs small. Do not reformat a whole file for a one-line change; run
  `make fmt` separately if formatting is the point.

## Documentation

- `docs/spec/` describes what the code does **today**. It changes in the same commit as
  the behavior.
- `docs/adr/` records decisions and their costs. An accepted ADR is immutable; a reversal
  is a new ADR.
- `docs/stdlib/` and the error catalog are generated. Edit the source (`std/*.lx`,
  `primitives.py`, the diagnostic registry) and run `make docs-sync`.
- Public pages declare `sources:` in the front matter; `make docs-fresh` reports pages whose
  sources changed after the page. Triage is recorded in `docs/log.md`.

## AI-assisted contributions

AI assistance is welcome. The contributor remains responsible for the result: you must
understand the change, run the tests, and be able to explain the diff in review. Disclose
substantial AI assistance in the PR description. Do not submit unreviewed mass-generated
PRs, and do not use an agent to bypass the syntax or feature gates.

## Security

Do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md) for the
private reporting channel and scope. Conduct reports are handled separately under the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Releases

Releases are cut by the maintainers by dispatching the **Release** workflow from `main`,
with the version already bumped in `pyproject.toml` (the input must match it). The workflow
builds and attests the wheel/sdist, then creates the `v<version>` tag and the GitHub
Release, and publishes to PyPI via Trusted Publishing. A manual `v*` tag push does not
start a release. Contributors do not need to bump the version or create tags.
