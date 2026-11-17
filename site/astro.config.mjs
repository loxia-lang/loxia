import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import starlight from '@astrojs/starlight';
import starlightLinksValidator from 'starlight-links-validator';

const repository = 'https://github.com/loxia-lang/loxia';

export default defineConfig({
  site: 'https://loxia-lang.github.io',
  base: '/loxia',
  trailingSlash: 'always',
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
          items: [
            { label: 'Why Loxia', link: '/why/' },
            { label: 'Learn Loxia', items: [{ autogenerate: { directory: 'learn' } }] },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Overview', link: '/reference/' },
            {
              label: '1.1 (next, Portuguese)',
              collapsed: true,
              items: [{ autogenerate: { directory: 'pt/reference' } }],
            },
            {
              label: '1.0 (stable, Portuguese)',
              collapsed: true,
              items: [{ autogenerate: { directory: 'pt/1.0/reference' } }],
            },
          ],
        },
        {
          label: 'Standard library',
          items: [{ autogenerate: { directory: 'stdlib' } }],
        },
        {
          label: 'Cookbook',
          items: [{ autogenerate: { directory: 'cookbook' } }],
        },
        { label: 'Changelog', link: '/changelog/' },
      ],
      head: [
        { tag: 'meta', attrs: { property: 'og:site_name', content: 'Loxia' } },
        { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary' } },
      ],
    }),
    sitemap(),
  ],
});
