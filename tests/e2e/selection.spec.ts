// Selection and regions end to end: select triangles, save them as a region,
// undo; paint with the brush and undo the stroke.

import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { launchApp, stubOpenDialog } from './support/app';
import { writeTorusStl } from './support/meshes';

test('saves selected triangles as a region and undoes it; brush strokes are undoable', async () => {
  const stl = path.join(mkdtempSync(path.join(tmpdir(), 'm2c-selection-')), 'torus.stl');
  writeTorusStl(stl);
  const { app, page } = await launchApp();

  try {
    await stubOpenDialog(app, stl);
    await page.getByTestId('empty-import').click();
    await expect(page.getByTestId('panel-import-mesh')).toBeVisible();
    await page.getByTestId('panel-ok').click();
    await page.evaluate(() => window.__m2cTest?.waitForIdle());

    // One slice of the torus: the first ten rings of 200 triangles.
    const faces = Array.from({ length: 2000 }, (_value, index) => index);
    await page.evaluate((selected) => window.__m2cTest?.selectFaces(selected), faces);
    await expect(page.getByTestId('status-selection')).toHaveText('2.000 Dreiecke ausgewählt');

    const canvas = page.getByTestId('viewport-canvas');
    await canvas.click({ button: 'middle' });
    await page.keyboard.press('Control+r');
    await expect(page.getByTestId('tree-group-regions')).toBeVisible();
    const revision = await page.evaluate(() => window.__m2cTest?.revision());

    await canvas.click({ button: 'middle' });
    await page.keyboard.press('Control+z');
    await expect(page.getByTestId('tree-group-regions')).toBeHidden();
    expect(await page.evaluate(() => window.__m2cTest?.revision())).toBe((revision ?? 1) - 1);

    // Clear the selection, then paint across the middle of the view with the brush.
    await page.keyboard.press('Control+d');
    await expect(page.getByTestId('status-selection')).toBeHidden();
    await page.getByTestId('tool-select-brush').click();
    await expect(page.getByTestId('selection-options')).toBeVisible();
    const box = (await canvas.boundingBox())!;
    const y = box.y + box.height / 2;
    await page.mouse.move(box.x + box.width * 0.2, y);
    await page.mouse.down();
    for (let step = 1; step <= 20; step += 1) {
      await page.mouse.move(box.x + box.width * (0.2 + (0.6 * step) / 20), y);
    }
    await page.mouse.up();
    await expect(page.getByTestId('status-selection')).toBeVisible();

    await page.keyboard.press('Control+z');
    await expect(page.getByTestId('status-selection')).toBeHidden();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('selection-options')).toBeHidden();
  } finally {
    await app.close();
  }
});
