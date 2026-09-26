import { builtinModules } from 'node:module';
import { fileURLToPath } from 'node:url';

import { defineConfig } from 'vite';

const root = fileURLToPath(new URL('.', import.meta.url));
const external = ['electron', ...builtinModules, ...builtinModules.map((name) => `node:${name}`)];

// Builds the Electron main process (`--mode main`) or the preload script
// (`--mode preload`) into a single CommonJS file each. A sandboxed preload cannot
// load other files, so everything it uses is bundled.
export default defineConfig(({ mode }) => {
  const target = mode === 'preload' ? 'preload' : 'main';
  return {
    resolve: { alias: { '@shared': `${root}src/shared` } },
    build: {
      outDir: `${root}dist/${target}`,
      emptyOutDir: true,
      target: 'node22',
      minify: false,
      sourcemap: true,
      ssr: true,
      lib: {
        entry: `${root}src/${target}/index.ts`,
        formats: ['cjs'],
        fileName: () => 'index.cjs',
      },
      rollupOptions: { external, output: { exports: 'auto' } },
    },
    ssr: { noExternal: true },
  };
});
