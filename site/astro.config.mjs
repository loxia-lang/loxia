// SPDX-License-Identifier: MIT OR Apache-2.0
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import starlight from '@astrojs/starlight';
import starlightLinksValidator from 'starlight-links-validator';

const repository = 'https://github.com/loxia-lang/loxia';
const base = '/loxia';

export default defineConfig({
  site: 'https://loxia-lang.github.io',
  base,
  trailingSlash: 'always',
  redirects: {
    '/1.0/reference/lexicon': `${base}/pt/1.0/reference/lexicon/`,
    '/1.0/reference/syntax': `${base}/pt/1.0/reference/syntax/`,
    '/1.0/reference/semantics': `${base}/pt/1.0/reference/semantics/`,
    '/1.0/reference/errors': `${base}/pt/1.0/reference/errors/`,
    '/1.0/reference/guarantees': `${base}/pt/1.0/reference/guarantees/`,
  },
  integrations: [
    starlight({
      title: 'Loxia',
      description:
        'A small, statically checked Lox dialect with a tree-walk interpreter and an optional LLVM backend.',
      defaultLocale: 'root',
      locales: {
        root: { label: 'English', lang: 'en' },
        pt: { label: 'Português', lang: 'pt-BR' },
      },
      social: [{ icon: 'github', label: 'GitHub', href: repository }],
      favicon: '/favicon.svg',
      customCss: ['./src/styles/custom.css'],
      lastUpdated: false,
      pagination: true,
      tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 3 },
      plugins: [
        starlightLinksValidator({
          errorOnRelativeLinks: false,
          errorOnFallbackPages: false,
          exclude: ['/loxia/404/'],
        }),
      ],
      sidebar: [
        {
          label: 'Start here',
          translations: { 'pt-BR': 'Comece aqui' },
          items: [
            { label: 'Why Loxia', translations: { 'pt-BR': 'Por que Loxia?' }, link: '/why/' },
            { label: 'Learn Loxia', translations: { 'pt-BR': 'Aprender Loxia' }, items: [{ autogenerate: { directory: 'learn' } }] },
          ],
        },
        {
          label: 'Reference',
          translations: { 'pt-BR': 'Referência' },
          items: [
            { label: 'Overview', translations: { 'pt-BR': 'Visão geral' }, link: '/reference/' },
            {
              label: '1.3 (current)',
              translations: { 'pt-BR': '1.3 (atual)' },
              collapsed: true,
              items: [{ autogenerate: { directory: 'reference' } }],
            },
            {
              label: '1.0 (archive, Portuguese)',
              translations: { 'pt-BR': '1.0 (arquivo, português)' },
              collapsed: true,
              items: [{ autogenerate: { directory: 'pt/1.0/reference' } }],
            },
          ],
        },
        {
          label: 'Standard library',
          translations: { 'pt-BR': 'Biblioteca padrão' },
          items: [{ autogenerate: { directory: 'stdlib' } }],
        },
        {
          label: 'Cookbook',
          translations: { 'pt-BR': 'Receitas' },
          items: [{ autogenerate: { directory: 'cookbook' } }],
        },
        { label: 'Changelog', translations: { 'pt-BR': 'Changelog' }, link: '/changelog/' },
      ],
      head: [
        { tag: 'meta', attrs: { property: 'og:site_name', content: 'Loxia' } },
        { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary' } },
      ],
    }),
    sitemap(),
  ],
});
