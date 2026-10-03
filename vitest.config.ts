import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const root = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@renderer': `${root}src/renderer`,
      '@shared': `${root}src/shared`,
    },
  },
  test: {
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx', 'tools/**/*.test.mjs'],
    environment: 'node',
    restoreMocks: true,
  },
});
