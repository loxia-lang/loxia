## Summary

<!-- What changed and why. Link the issue or ADR when there is one. -->

## Related

- Issue: <!-- Closes #... -->
- ADR: <!-- docs/adr/NNNN-... -->

## Type of change

- [ ] Bug fix
- [ ] New feature (no syntax change)
- [ ] Syntax change (requires human approval and the ADR-0066 four questions)
- [ ] Documentation or tooling
- [ ] CI, packaging or dependencies

## Checklist

- [ ] `make check` passes (or I explain what could not run locally).
- [ ] Tests were added or updated; a bug fix has a regression case.
- [ ] `docs/spec/` was updated if observable behavior changed.
- [ ] An ADR was added or updated if this is a design decision.
- [ ] Generated files were regenerated (`make docs-sync`, `make grammar`, `make primitives`), not hand-edited.
- [ ] Commits are signed off (`git commit -s`) and the PR title follows Conventional Commits.
- [ ] `AGENTS.md` (and the matching scoped file) updated if a command, layer or rule changed.
- [ ] No secrets or private paths are included.

## Syntax change (only if applicable)

Answer the four ADR-0066 questions:

1. Which existing spelling or stdlib function does it replace?
2. Is it locally decidable?
3. Does it fit the current precedence?
4. Is there exactly one canonical form?

Backend and formatter impact:

## AI assistance

<!-- Disclose substantial AI assistance and confirm you understand and tested the diff. -->

## Notes for reviewers

<!-- Trade-offs, follow-ups, or anything intentionally out of scope. -->
