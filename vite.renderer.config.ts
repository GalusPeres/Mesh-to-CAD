import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const root = fileURLToPath(new URL('.', import.meta.url));

// The renderer is loaded from the custom `m2c://app/` scheme in production,
// so every asset URL must be relative (`base: './'`).
export default defineConfig({
  root: `${root}src/renderer`,
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@renderer': `${root}src/renderer`,
      '@shared': `${root}src/shared`,
    },
  },
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  build: {
    outDir: `${root}dist/renderer`,
    emptyOutDir: true,
    sourcemap: true,
    chunkSizeWarningLimit: 1600,
  },
});
