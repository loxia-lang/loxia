---
sources:
  - tools/docs_common.py
  - tools/docs_index.py
  - loxia/docs_index.py
  - tests/test_docs_index.py
---

# Documentation index

`loxia/_spec/index.json` is the machine-readable projection of the language reference. It
is generated from `docs/spec/*.md` and `docs/stdlib/*.md`, shipped inside the wheel and
consumed by the runtime module `loxia/docs_index.py`. The decision and its trade-offs are
in [ADR-0111](../adr/0111-indice-de-documentacao.md).

The site is the other consumer: `tools/docs_common.py` is the single source of page
slugs and canonical URLs, so the index and the Starlight routes cannot drift. The same
command writes `site/public/llms.txt`, a page-level catalog served at
`https://loxia-lang.github.io/loxia/llms.txt`.

## Commands

```bash
make docs-index                 # writes the JSON and llms.txt
make docs-sync                  # levels + codes + stdlib + docs index
uv run python tools/docs_index.py --check   # CI gate: must be up to date
```

`docs-sync` is the normal path after editing `docs/spec/` or running `make stdlib-docs`.
`tests/test_docs_index.py` runs the `--check` gate, so a stale artifact fails the suite.

## Schema (version 1)

```json
{
  "schema_version": 1,
  "loxia_version": "1.1.0",
  "pages": [
    {
      "id": "spec/syntax",
      "kind": "spec",
      "title": "Syntax",
      "path": "docs/spec/sintaxe.md",
      "url": "https://loxia-lang.github.io/loxia/reference/syntax/",
      "summary": "Grammar of the current parser ...",
      "sources": ["loxia_core/frontend/parser.py"],
      "sections": [
        {
          "id": "spec/syntax#optional-semicolon",
          "anchor": "optional-semicolon",
          "title": "Optional semicolon",
          "level": 2,
          "line_start": 246,
          "line_end": 300,
          "url": "https://loxia-lang.github.io/loxia/reference/syntax/#optional-semicolon",
          "text": "## Optional semicolon\n\n..."
        }
      ]
    }
  ]
}
```

- **Page ids** use the site slug: `spec/lexicon`, `spec/syntax`, `spec/semantics`,
  `spec/errors`, `spec/guarantees`; stdlib pages are `stdlib/<file>` (`stdlib/index` for
  the landing page).
- **Section ids** are `<page-id>#<anchor>`. Anchors follow `github-slugger`: lower-case,
  punctuation removed, spaces to `-`, duplicates suffixed `-1`, `-2`, ... This is the same
  id Starlight emits, so links copied from the site resolve in the index.
- **Lines** are 1-based; `line_end` is exclusive and points at the next heading of the
  same or a higher level (or one past EOF). `text` includes child headings, with links
  rewritten to canonical site/GitHub URLs.
- **Order** is fixed: the five spec pages in reading order, then `stdlib/index`, then the
  remaining stdlib pages alphabetically. Sections follow source order.
- **No volatile data**: no timestamps, git hashes, absolute paths or environment values.

## Runtime API

```python
from loxia.docs_index import load_index

index = load_index()
index.section("spec/syntax#optional-semicolon")  # Section | None
index.find_page("spec/sintaxe.md")  # Page | None
index.search("optional semicolon", limit=5)  # tuple[Section, ...]
```

`load_index()` reads the packaged resource with `importlib.resources`, validates the
schema version and caches the result. `search` is deliberately simple and deterministic:
exact section id, exact page id, title match (exact/prefix/substring), then body match;
ties break by page order and source line. There is no fuzzy matching, embeddings or
network access. The future MCP `loxia_spec` tool is a thin wrapper over this API; the
protocol/sandbox decisions live in the MCP ADR, not here.

## Alignment with the site

`tools/docs_common.py` owns `SPEC_PAGES`, `SPEC_SLUGS`, `slugify`, `spec_url`,
`stdlib_url` and the front-matter helpers. `tools/docs_site.py` imports them too, so a
change to a slug or URL affects both outputs. When `site/dist` exists **and is not older
than the docs**, the test suite compares every index anchor with the ids in the generated
HTML; a stale local build is skipped (run `npm run build --prefix site`). In CI the
algorithm fixtures (`grammar-ebnf`, `type-checker---check`, `equality--`, duplicate
`syntax-1`) plus the sync gate cover the same contract without a Node build.

## Non-goals

- ADRs, `docs/tech/` and the roadmap are **not** indexed; they explain *why*, are partly
  in Portuguese and change on a different cadence.
- The index is not a search engine or a vector store; it is a deterministic catalog.
- The site remains the human-facing rendering; the index is not a replacement for it.
