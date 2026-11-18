---
title: Reference
description: The normative Loxia language reference.
---

The normative reference describes what the language does **today**. It is written in
English and generated from `docs/spec/`.

## Current reference — 1.1

- [Lexicon](lexicon/)
- [Syntax](syntax/)
- [Semantics](semantics/)
- [Errors](errors/)
- [Guarantees](guarantees/)

## Archived reference — 1.0

The 1.0 reference is frozen at the `v1.0.0` tag and kept for programs that still target
the first release:

- [1.0 reference (Portuguese)](../pt/1.0/reference/lexicon/)

## How the site is built

The reference is generated from the Markdown in `docs/spec/` and
`docs/versions/1.0/reference/`. Each page shows the source commit it was verified against.
The design is recorded in [ADR-0103](https://github.com/loxia-lang/loxia/blob/main/docs/adr/0103-site-de-documentacao-e-versionamento.md).
