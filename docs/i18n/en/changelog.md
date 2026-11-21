---
title: Changelog
description: Release notes and the history of Loxia.
---

The canonical changelog is maintained in the repository at
[`CHANGELOG.md`](https://github.com/loxia-lang/loxia/blob/main/CHANGELOG.md).

The first public release was **1.1.0**; **1.2.0** is the current release, published on
[PyPI](https://pypi.org/project/loxia/). Historical changelog entries before 1.1.0 are
written in Portuguese.

## 1.2.0

Loxia 1.2.0 is the first PyPI release with the MCP server:

- `loxia mcp` and `loxia-mcp` expose `loxia_check`, `loxia_run`, `loxia_ast`,
  `loxia_spec`, `loxia_explain` and `loxia_version` over MCP `2026-07-28` on stdio;
- `loxia_run` uses the sandbox profile (filesystem/process primitives denied, timeouts and
  resource limits);
- the package includes the MCP Registry manifest and the `mcp-name` marker for PyPI
  ownership verification;
- the Inspector documentation covers the modern protocol era and local checkout setup.

The exact notes are curated in the canonical changelog.

## 1.1.0

The 1.1.0 release brought the public repository, packaging, the documentation site and the
accumulated post-1.0 work to PyPI. The exact notes are curated in the canonical changelog;
the [GitHub Release](https://github.com/loxia-lang/loxia/releases/tag/v1.1.0) links the
artifacts.
