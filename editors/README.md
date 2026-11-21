# Editors — grammar assets

The TextMate grammar and its Shiki/DSH wrappers live in **`editors/grammar/`**. They are
**generated** from the language sources and shipped as release assets; the VS Code client
lives in its own repository, [`loxia-lang/loxia-vscode`](https://github.com/loxia-lang/loxia-vscode).

| File | Consumer |
| --- | --- |
| `grammar/loxia.tmLanguage.json` | VS Code, Sublime Text, TextMate and any TextMate-compatible editor |
| `grammar/loxia.mjs` | Shiki (docs site, harness viewer) |
| `grammar/loxia.ts` | DeepSeek Harness viewer (self-contained Shiki registration) |
| `grammar/SHA256SUMS` | Generated on release, never committed |

## VS Code extension

Install **Loxia** from the [Marketplace](https://marketplace.visualstudio.com/items?itemName=loxia-lang.loxia)
or [Open VSX](https://open-vsx.org/extension/loxia-lang/loxia). The extension provides syntax
highlighting, the LSP client (diagnostics, hover, completion, inlay hints, formatting,
rename and symbols), and **Run** (interpreted or compiled). The client is versioned
independently and requires the `loxia` CLI for the language server and the run commands.

The extension repo consumes the grammar from the GitHub Release, not from a hand copy:

```bash
# in loxia-vscode
npm run grammar:sync -- --version 1.1.0
```

`grammar.lock.json` pins the language release and the SHA-256 of the JSON, so the VSIX
build is reproducible and a grammar change is a reviewed diff.

## Release contract

Every `vX.Y.Z` release of `loxia-lang/loxia` attaches:

- `loxia.tmLanguage.json`
- `loxia.mjs`
- `loxia.ts`
- `SHA256SUMS`

The [release workflow](../.github/workflows/release.yml) runs
`uv run python editors/build_grammar.py --check` and then
`--assets dist-grammar`; the `grammar` artifact is uploaded to the GitHub Release next to
the wheel/sdist. Consumers should verify `SHA256SUMS` before using an asset.

## The grammar is generated — do not edit the JSON

`editors/build_grammar.py` builds the files from:

| Source | What it contributes |
| --- | --- |
| `loxia_core/frontend/keywords.py` (`KEYWORDS`) | all keywords, grouped by scope |
| `loxia_core/frontend/token_type.py` (`TokenType`) | operators (`**`, `??`, `?.`, `..`, `>>>`…) and punctuation |
| `loxia_core/execution/prelude.py` (`BUILTIN_NAMES`) | `Int`, `Result`, `RuntimeError`, `len`, `math`… |

```bash
make grammar                                    # uv run python editors/build_grammar.py --write
make grammar-assets                             # + SHA256SUMS in dist-grammar/
uv run python editors/build_grammar.py --check  # exit 1 if any generated file is stale
```

`tests/test_editor_grammar.py` runs `--check` in `make check`, so a new
keyword/operator without `make grammar` breaks the build — highlighting never rots.
Categorizing a new keyword is a human decision: `KEYWORD_GROUPS` in `build_grammar.py`
must cover `KEYWORDS` exactly, and the generator deliberately fails if one is missing or
extra.

## Sublime Text / TextMate

Download `loxia.tmLanguage.json` from the release and copy it into the editor's package
directory (on Sublime, a directory under `Packages/`; on TextMate,
`~/Library/Application Support/TextMate/Bundles`).

## Shiki (docs site and harness viewer)

`editors/grammar/loxia.mjs` exposes the **same** grammar (the same JSON, no copy) in the
format Shiki consumes — `LanguageRegistration[]` with `name: 'loxia'` and alias `lx`. It
is generated together with the JSON (`make grammar`), so it cannot drift.

```js
import loxia from './editors/grammar/loxia.mjs'
// shiki: createHighlighterCoreSync({ langs: [loxia], ... }) → codeToTokens(..., { lang: 'loxia' })
```

### DeepSeek Harness viewer

The viewer also uses Shiki, but with an **explicit allowlist**: a language outside the
table renders as plain text, and there is no plugin hook for registering a grammar. Making
`.lx` appear there is a **3-point + 1-file** patch in the harness checkout:

1. copy `editors/grammar/loxia.ts` to
   `packages/client/ui-primitives/src/markdown/grammars/loxia.ts` (self-contained,
   with no dependency on this repo);
2. in `packages/util/code-language/src/index.ts`, in the `LANGUAGE_EXTENSIONS`
   table: `loxia: ['lx'],`
3. in `packages/client/ui-primitives/src/markdown/highlight.ts`:
   - at the end of `LAZY_GRAMMARS`: `['loxia', () => import('./grammars/loxia')],`
   - in `LANG_ALIASES`: `['loxia', 'loxia'], ['lx', 'loxia'],`

Then rebuild/reload the harness (`make check` or `pnpm -r test` in its checkout). The
`loxia.ts` file is generated here by `make grammar`, so updating the grammar requires
regenerating and recopying — the drift between the two repos is intentional: the harness
does not depend on this repo (and this repo does not depend on the harness).

## Declared limitations

- **Nested `/* */`** works up to 3 levels (`NESTING`); after that it closes at the first
  `*/`. This is the same hack C/JS grammars use — TextMate has no real recursion.
- **No semantic analysis**: a capitalized `Foo` becomes `entity.name.type` even when it is
  a variable; a field after `.` is not refined.
- **`//` is division**, not a comment (ADR-0012). No comment rule may use `//` — there is
  a test for that.
- Highlighting on `github.com` stays colorless until the language lands in linguist; the
  root `.gitattributes` keeps `.lx` files out of the repo's statistics
  (`linguist-detectable=false`) instead of marking them as another language.
