# Editors — syntax highlighting and the Loxia LSP client

**TextMate** grammar (`syntaxes/loxia.tmLanguage.json`) + a VS Code extension with an LSP
client (diagnostics, formatting, completion, code actions and rename). The same file works
in Sublime Text, TextMate, VS Code and, once the language lands in
[linguist](https://github.com/github-linguist/linguist), on `github.com` — linguist requires
a vendored TextMate grammar and 2,000+ `.lx` files in public repos (see `TODO.md` §14).

## Install in VS Code

**Quick way (one line, nothing installed):**

```bash
code --extensionDevelopmentPath="$PWD/editors/vscode" .
```

VS Code opens with the extension loaded in development mode. Open an `.lx` file and the
status bar should show **Loxia** (not "Plain Text") — from there the theme highlights it.

**"Installed" way (leaves development mode):**

```bash
ln -s "$PWD/editors/vscode" ~/.vscode/extensions/loxia-1.0.0
```

and reload the window (`Developer: Reload Window` / `Ctrl+Shift+P`). Or, inside
`editors/vscode`, press `F5` — `.vscode/launch.json` is already there and opens the
*Extension Development Host* with the extension loaded.

### No colors? Check these in order

1. **Status bar says "Plain Text"?** The extension was not loaded: `.lx` is not recognized.
   Check `~/.vscode/extensions | grep loxia` and reload the window; `F5` **without** the
   `launch.json` only opens the "Select environment" dialog and loads nothing.
2. **Status bar says "Loxia" but everything is gray?** The file is being read as `loxia`
   but the theme does not map the scopes. `Ctrl+Shift+P` → **Developer: Inspect Editor
   Tokens and Scopes** and click a keyword: the scopes should list
   `keyword.control.loxia` etc. If they do, it is the theme (switch to Dark+ to test); if
   not, it is the grammar.
3. **`F5` complains about "Select environment"?** The `launch.json` is missing — it has
   existed in this directory since editor 1.0.0; make sure you opened `editors/vscode` as
   the **workspace** (not the repo root).
4. **Did you open the `.lx` before installing?** Close and reopen the file: the language
   mode is decided when the file opens and is not re-evaluated immediately.

## LSP client (VS Code)

The extension starts `loxia lsp` (configurable through `loxia.server.path` /
`loxia.server.args`) and uses the same contract as the CLI. Details and configuration for
running from the checkout are in [`vscode/README.md`](vscode/README.md); the client has no
npm dependencies and is a candidate for its own repo (`loxia-editors`) in the future.

## Sublime Text / TextMate

Copy `vscode/syntaxes/loxia.tmLanguage.json` into the editor's package directory (on
Sublime, a directory under `Packages/`; on TextMate,
`~/Library/Application Support/TextMate/Bundles`).

## The grammar is generated — do not edit the JSON

`editors/build_grammar.py` builds the JSON from:

| Source | What it contributes |
| --- | --- |
| `loxia_core/frontend/keywords.py` (`KEYWORDS`) | all 32 keywords, grouped by scope |
| `loxia_core/frontend/token_type.py` (`TokenType`) | operators (`**`, `??`, `?.`, `..`, `>>>`…) and punctuation |
| `loxia_core/execution/prelude.py` (`BUILTIN_NAMES`) | `Int`, `Result`, `RuntimeError`, `len`, `math`… |

```bash
make grammar       # uv run python editors/build_grammar.py --write
uv run python editors/build_grammar.py --check   # exit 1 if the JSON is stale
```

`tests/test_editor_grammar.py` runs the `--check` in `make check`, so a new
keyword/operator without `make grammar` breaks the build — highlighting never rots.

Categorizing a new keyword is a human decision: `KEYWORD_GROUPS` in `build_grammar.py`
must cover `KEYWORDS` exactly, and the generator deliberately fails if one is missing or
extra.

## Shiki (docs site and harness viewer)

`editors/shiki/loxia.mjs` exposes the **same** grammar (the same JSON, no copy) in the
format Shiki consumes — `LanguageRegistration[]` with `name: 'loxia'` and alias `lx`. It
is generated together with the JSON (`make grammar`), so it cannot drift.

```js
import loxia from './editors/shiki/loxia.mjs'
// shiki: createHighlighterCoreSync({ langs: [loxia], ... }) → codeToTokens(..., { lang: 'loxia' })
```

### DeepSeek Harness viewer

The viewer also uses Shiki, but with an **explicit allowlist**: a language outside the
table renders as plain text, and there is no plugin hook for registering a grammar. Making
`.lx` appear there is a **3-point + 1-file** patch in the harness checkout:

1. copy `editors/dsh/loxia.ts` to
   `packages/client/ui-primitives/loxia_core/markdown/grammars/loxia.ts` (self-contained,
   with no dependency on this repo);
2. in `packages/util/code-language/loxia_core/index.ts`, in the `LANGUAGE_EXTENSIONS`
   table: `loxia: ['lx'],`
3. in `packages/client/ui-primitives/loxia_core/markdown/highlight.ts`:
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
- **`//` is division**, not a comment (ADR-0012). No comment rule may use `//` — there is a
  test for that.
- Highlighting on `github.com` stays colorless until the language lands in linguist; the
  root `.gitattributes` keeps `.lx` files out of the repo's statistics
  (`linguist-detectable=false`) instead of marking them as another language.
