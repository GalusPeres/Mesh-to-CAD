import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { launchApp, stubOpenDialog } from './support/app';
import { writeTorusStl } from './support/meshes';

test('starts securely, imports a scan, shows it and undoes the import', async () => {
  const stl = path.join(mkdtempSync(path.join(tmpdir(), 'm2c-smoke-')), 'torus.stl');
  const faces = writeTorusStl(stl);
  const { app, page } = await launchApp();

  try {
    const renderersSandboxed = await app.evaluate(({ app: electronApp }) =>
      electronApp
        .getAppMetrics()
        .filter((metric) => metric.type === 'Tab')
        .every((metric) => metric.sandboxed === true),
    );
    expect(renderersSandboxed).toBe(true);
    const nodeGlobals = await page.evaluate(() => {
      const scope = window as unknown as Record<string, unknown>;
      return [typeof scope.require, typeof scope.process, typeof scope.module];
    });
    expect(nodeGlobals).toEqual(['undefined', 'undefined', 'undefined']);

    await expect(page.getByTestId('empty-import')).toBeVisible();
    await stubOpenDialog(app, stl);
    await page.getByTestId('empty-import').click();

    await expect(page.getByTestId('panel-import-mesh')).toBeVisible();
    await page.getByTestId('panel-ok').click();
    await expect(page.getByTestId('status-faces')).toHaveText('50.000 Dreiecke');
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    expect(await page.evaluate(() => window.__m2cTest?.scene().scanFaces)).toBe(faces);
    await page.screenshot({ path: 'test-results/smoke-imported.png' });

    await page.getByTestId('viewport-canvas').click({ button: 'middle' });
    await page.keyboard.press('Control+z');
    await expect(page.getByTestId('empty-import')).toBeVisible();
    expect(await page.evaluate(() => window.__m2cTest?.revision())).toBe(0);
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    expect(await page.evaluate(() => window.__m2cTest?.scene().scanFaces)).toBe(0);
  } finally {
    await app.close();
  }
});
