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

test('Freiform-Netz lays a net over the scan, shows the deviation and becomes a body', async () => {
  test.setTimeout(240_000);
  const folder = mkdtempSync(path.join(tmpdir(), 'm2c-freeform-net-'));
  const stl = path.join(folder, 'torus.stl');
  writeTorusStl(stl);
  const { app, page } = await launchApp();

  try {
    await stubOpenDialog(app, stl);
    await page.getByTestId('empty-import').click();
    await page.getByTestId('panel-ok').click();
    await page.evaluate(() => window.__m2cTest?.waitForIdle());

    await page.getByTestId('stage-model').click();
    await page.getByTestId('tool-freeform-net').click();
    await page.getByRole('radio', { name: 'Grob' }).click();
    await page.getByTestId('freeform-net-generate').click();

    const panel = page.getByTestId('panel-freeform-net');
    await expect(panel).toContainText('Vierecke', { timeout: 120_000 });
    await expect(panel).toContainText('Geschlossener Körper');
    await expect(panel).toContainText('Innerhalb der Toleranz', { timeout: 60_000 });
    await page.screenshot({ path: 'test-results/freeform-net-heatmap.png' });

    // Snap all points to the scan once more; the draft history gets a step.
    await page.getByTestId('freeform-net-fit').click();
    await expect(page.getByTestId('freeform-net-fit')).toBeEnabled({ timeout: 60_000 });

    await page.getByTestId('panel-ok').click();
    await expect(page.getByTestId('panel-freeform-net')).toHaveCount(0, { timeout: 120_000 });
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    const snapshot = await page.evaluate(async () => {
      const response = (await window.m2c.kernel.request({
        clientId: 9_200_000,
        method: 'doc.get',
        params: {},
        buffers: [],
      })) as { ok: boolean; result?: unknown };
      return response.result as Snapshot;
    });
    const feature = snapshot.document.features.find((item) => item.type === 'freeformNet');
    expect(feature).toBeDefined();
    const body = snapshot.status.bodies.find((item) => item.id === feature?.id);
    expect(body?.valid).toBe(true);
    expect(body?.faceTags.every((tag) => tag.includes(':patch:'))).toBe(true);
    await page.screenshot({ path: 'test-results/freeform-net-body.png' });
  } finally {
    await app.close();
  }
});
