import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { type ElectronApplication, expect, test } from '@playwright/test';

import { ROOT, launchApp, stubOpenDialog } from './support/app';

// Documentation screenshots of the real app (docs/images). Opt-in, because the scan is
// not part of the repository and surfacing it takes a while:
//   M2C_SCREENSHOT_SCAN=path/to/scan.ply npx playwright test screenshots
const scan = process.env.M2C_SCREENSHOT_SCAN;
const images = path.join(ROOT, 'docs', 'images');

async function stubSaveDialog(app: ElectronApplication, file: string): Promise<void> {
  await app.evaluate(({ dialog }, chosen) => {
    dialog.showSaveDialog = () => Promise.resolve({ canceled: false, filePath: chosen });
  }, file);
}

test.skip(!scan, 'set M2C_SCREENSHOT_SCAN to a scan file');

test('documentation screenshots: import, Auto-Flächen, STEP export', async () => {
  test.setTimeout(900_000);
  const { app, page } = await launchApp({ gpu: true });
  try {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await stubOpenDialog(app, scan!);
    await page.getByTestId('empty-import').click();
    await expect(page.getByTestId('panel-import-mesh')).toBeVisible();
    await page.getByTestId('panel-ok').click({ timeout: 120_000 });
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    await page.screenshot({ path: path.join(images, '01-scan-imported.png') });

    await page.getByTestId('stage-model').click();
    await page.getByTestId('tool-auto-surface').click();
    await page.getByRole('radio', { name: 'Mittel' }).first().click();
    const result = page.getByTestId('auto-surface-result');
    await expect(result).toContainText('Gültiger Körper', { timeout: 600_000 });
    await page.screenshot({ path: path.join(images, '02-auto-surface.png') });
    await page.getByTestId('panel-ok').click();
    await page.evaluate(() => window.__m2cTest?.waitForIdle());

    await page.getByTestId('stage-inspect').click();
    const step = path.join(mkdtempSync(path.join(tmpdir(), 'm2c-shots-')), 'armadillo.step');
    await stubSaveDialog(app, step);
    await page.getByTestId('tool-export-step').click();
    await expect(page.getByTestId('panel-export-step')).toBeVisible();
    await page.getByTestId('panel-ok').click();
    await expect(page.getByTestId('export-done')).toContainText('STEP gespeichert', {
      timeout: 300_000,
    });
    await page.screenshot({ path: path.join(images, '03-step-export.png') });
  } finally {
    await app.close();
  }
});
