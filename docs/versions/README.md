# Reference snapshots

This directory keeps frozen reference snapshots for the documentation site. A snapshot is
generated once from a release tag and committed; the site build never checks out the tag.

```bash
uv run python tools/docs_versions.py --version 1.0 --tag v1.0.0
```

The generator rewrites links: spec pages point to each other with relative site links, and
links to ADRs/roadmap files point at the tag on GitHub. Each version has a `manifest.json`
with the tag, the peeled commit and the source page list.

The current reference lives in `docs/spec/`, is written in English and is versioned by the
release itself; only archived releases get a directory here. The 1.0 archive remains
Portuguese-only (ADR-0102/ADR-0103).
