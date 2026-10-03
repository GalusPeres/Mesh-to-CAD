import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { launchApp, stubOpenDialog } from './support/app';
import { writeTorusStl } from './support/meshes';

interface Snapshot {
  document: { features: { id: string; type: string }[] };
  status: { bodies: { id: string; valid: boolean; faceTags: string[] }[] };
}

test('Auto-Flächen turns a closed scan into a valid B-spline body', async () => {
  test.setTimeout(240_000);
  const folder = mkdtempSync(path.join(tmpdir(), 'm2c-auto-surface-'));
  const stl = path.join(folder, 'torus.stl');
  writeTorusStl(stl);
  const { app, page } = await launchApp();

  try {
    await stubOpenDialog(app, stl);
    await page.getByTestId('empty-import').click();
    await page.getByTestId('panel-ok').click();
    await page.evaluate(() => window.__m2cTest?.waitForIdle());

    await page.getByTestId('stage-model').click();
    await page.getByTestId('tool-auto-surface').click();
    await page.getByRole('radio', { name: 'Grob' }).click();

    const result = page.getByTestId('auto-surface-result');
    await expect(result).toContainText('Gültiger Körper', { timeout: 180_000 });
    await expect(result).toContainText('Flächen');
    await expect(result).toContainText('Abweichung RMS');
    await page.screenshot({ path: 'test-results/auto-surface-preview.png' });

    await page.getByTestId('panel-ok').click();
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    const snapshot = await page.evaluate(async () => {
      const response = (await window.m2c.kernel.request({
        clientId: 9_100_000,
        method: 'doc.get',
        params: {},
        buffers: [],
      })) as { ok: boolean; result?: unknown };
      return response.result as Snapshot;
    });
    const feature = snapshot.document.features.find((item) => item.type === 'autoSurface');
    expect(feature).toBeDefined();
    const body = snapshot.status.bodies.find((item) => item.id === feature?.id);
    expect(body?.valid).toBe(true);
    expect(body?.faceTags.every((tag) => tag.includes(':patch:'))).toBe(true);
  } finally {
    await app.close();
  }
});
