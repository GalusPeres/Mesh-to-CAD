import { defineConfig } from '@playwright/test';

// End-to-end tests launch the built Electron app (`npm run build` first).
export default defineConfig({
  testDir: 'tests/e2e',
  outputDir: 'test-results',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/report.json' }]],
});
