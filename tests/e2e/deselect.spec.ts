// Clearing the selection without knowing a shortcut: a click into empty space
// with a selection tool, and the clear button next to the count in the status bar.

import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { launchApp, stubOpenDialog } from './support/app';
import { writeTorusStl } from './support/meshes';

test('a click into empty space and the status bar button clear the selection', async () => {
  const stl = path.join(mkdtempSync(path.join(tmpdir(), 'm2c-deselect-')), 'torus.stl');
  writeTorusStl(stl);
  const { app, page } = await launchApp();

  try {
    await stubOpenDialog(app, stl);
    await page.getByTestId('empty-import').click();
    await page.getByTestId('panel-ok').click();
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    const faces = Array.from({ length: 2000 }, (_value, index) => index);
    const status = page.getByTestId('status-selection');

    await page.evaluate((selected) => window.__m2cTest?.selectFaces(selected), faces);
    await expect(status).toBeVisible();
    await page.getByTestId('status-selection-clear').click();
    await expect(status).toBeHidden();

    const canvas = page.getByTestId('viewport-canvas');
    const box = (await canvas.boundingBox())!;
    const corner = { x: box.x + 30, y: box.y + box.height - 30 };
    for (const tool of ['tool-select-brush', 'tool-select-smart', 'tool-select-rectangle']) {
      await page.evaluate((selected) => window.__m2cTest?.selectFaces(selected), faces);
      await expect(status).toBeVisible();
      await page.getByTestId(tool).click();
      await page.mouse.click(corner.x, corner.y);
      await expect(status, tool).toBeHidden();
      await page.keyboard.press('Escape');
    }
  } finally {
    await app.close();
  }
});
