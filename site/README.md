# Loxia documentation site

The public documentation site is built with [Astro Starlight](https://starlight.astro.build/)
and lives in this directory. **Do not edit `src/content/docs/`**: it is generated from
`docs/` by `../tools/docs_site.py` and ignored by git.

```bash
npm ci
npm run dev       # generates content and starts the dev server
npm run build     # generates content and builds dist/
npm run preview
```

From the repository root:

```bash
make docs-dev
make docs-build
make docs-links
```

Content sources:

- `docs/spec/` → Portuguese reference 1.1 (`/pt/reference/*`)
- `docs/versions/1.0/reference/` → frozen Portuguese reference 1.0
- `docs/stdlib/` → standard library reference (English)
- `docs/i18n/en/` → English home, why, learn, cookbook, changelog and reference landing
- `docs/i18n/pt/` → optional Portuguese translations

ADRs, `TODO.md`, `IDEIAS.md`, `TIPOS.md`, `ESCOPO.md` and `docs/log.md` are intentionally not
published. See [ADR-0103](../docs/adr/0103-site-de-documentacao-e-versionamento.md).

Additional checks:

```bash
make docs-links        # internal links in the built HTML
make docs-i18n-check   # translated_from/source status
```
