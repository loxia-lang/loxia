# Documentation translations

The English site is the default locale, but the normative reference is currently in
Portuguese. Translations live here as a mirror of the source paths:

```text
docs/i18n/en/reference/lexicon.md   # English translation of docs/spec/lexico.md
docs/i18n/pt/learn/values.md        # optional Portuguese translation of the English page
```

A translated page declares its provenance in the front matter:

```yaml
---
title: Lexicon
translated_from: 1a2b3c4
source: docs/spec/lexico.md
---
```

`source` is the file the translation came from; `translated_from` is the short commit of
that source when the translation was made. `make docs-i18n-check` reports pages whose
source changed after that commit. The site shows the translation status and never
translates at build time.

English-original pages (`learn`, `why`, `cookbook`) do not use `translated_from`; only the
reference translation does. ADRs are not translated on the site.
