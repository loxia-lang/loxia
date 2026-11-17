import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

// Keep dots in slugs (the archived version is `1.0`, not `10`).
const generateId = ({ entry }: { entry: string }) => entry.replace(/\.(md|mdx)$/, '');

export const collections = {
  docs: defineCollection({ loader: docsLoader({ generateId }), schema: docsSchema() }),
};
