import path from 'node:path';

import { type ElectronApplication, type Page, _electron as electron } from '@playwright/test';

import type {} from '../../../src/shared/testHooks';

export const ROOT = path.resolve(import.meta.dirname, '..', '..', '..');

/**
 * Launch the built app (`npm run build`) in test mode, or the packaged app when
 * `M2C_APP_BINARY` is set. Test mode enables the test hooks and software WebGL.
 */
export async function launchApp(): Promise<{ app: ElectronApplication; page: Page }> {
  const env: Record<string, string> = { ...(process.env as Record<string, string>), M2C_E2E: '1' };
  delete env.ELECTRON_RUN_AS_NODE;
  const binary = process.env.M2C_APP_BINARY;
  const app = await electron.launch(
    binary
      ? { executablePath: binary, env }
      : { args: [path.join(ROOT, 'dist', 'main', 'index.cjs')], env },
  );
  const page = await app.firstWindow();
  await page.waitForFunction(() => window.__m2cTest?.revision() === 0, undefined, {
    timeout: 60_000,
  });
  return { app, page };
}

/** Make the next native open dialog return `file` without showing a dialog. */
export async function stubOpenDialog(app: ElectronApplication, file: string): Promise<void> {
  await app.evaluate(({ dialog }, chosen) => {
    dialog.showOpenDialog = () => Promise.resolve({ canceled: false, filePaths: [chosen] });
  }, file);
}
