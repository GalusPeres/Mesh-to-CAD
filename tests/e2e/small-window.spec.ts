import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { launchApp, stubOpenDialog } from './support/app';
import { writeTorusStl } from './support/meshes';

// A laptop at 150 % scaling offers about 1280 x 650 logical pixels below the title bar.
// Panel buttons and the status bar must stay inside the window.
const SMALL = { width: 1280, height: 650 };

test('layout fits a small window: panel footer and status bar stay visible', async () => {
  const { app, page } = await launchApp();
  try {
    await page.setViewportSize(SMALL);

    const scan = path.join(mkdtempSync(path.join(tmpdir(), 'm2c-small-')), 'torus.stl');
    writeTorusStl(scan);
    await stubOpenDialog(app, scan);
    await page.getByTestId('empty-import').click();
    await page.getByTestId('panel-ok').click({ timeout: 60_000 });
    await page.evaluate(() => window.__m2cTest?.waitForIdle());

    await page.getByTestId('stage-model').click();
    await page.getByTestId('tool-fit-primitive').click();
    const ok = page.getByTestId('panel-ok');
    await expect(ok).toBeVisible();

    const inside = async (selector: string) =>
      page.evaluate((css) => {
        const box = document.querySelector(css)?.getBoundingClientRect();
        return !!box && box.bottom <= window.innerHeight && box.right <= window.innerWidth;
      }, selector);
    expect(await inside('[data-testid="panel-ok"]')).toBe(true);
    expect(await inside('footer')).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      SMALL.width,
    );

    if (process.env.M2C_SMALL_WINDOW_SHOT) {
      await page.screenshot({ path: process.env.M2C_SMALL_WINDOW_SHOT });
    }
  } finally {
    await app.close();
  }
});
