# Loxia documentation site

The public documentation site is built with [Astro Starlight](https://starlight.astro.build/)
and lives in this directory. **Do not edit `src/content/docs/`**: it is generated from
`docs/` by `../tools/docs_site.py` and ignored by git. The same content step also writes
`public/llms.txt` and `../loxia/_spec/index.json` via `../tools/docs_index.py` (ADR-0111).

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
make docs-index     # only the JSON/llms.txt artifacts
```

Content sources:

- `docs/spec/` → English reference 1.1 (`/reference/*`, with `/pt/reference/*` as fallback)
- `docs/versions/1.0/reference/` → frozen Portuguese reference 1.0
- `docs/stdlib/` → standard library reference (English)
- `docs/i18n/en/` → English home, why, learn, cookbook, changelog and reference landing
- `docs/i18n/pt/` → optional Portuguese translations

ADRs, `TODO.md`, `IDEIAS.md`, `TIPOS.md`, `docs/roadmap.md` and `docs/log.md` are intentionally not
published. See [ADR-0103](../docs/adr/0103-site-de-documentacao-e-versionamento.md).

Additional checks:

```bash
make docs-links        # internal links in the built HTML
make docs-i18n-check   # translated_from/source status
```
