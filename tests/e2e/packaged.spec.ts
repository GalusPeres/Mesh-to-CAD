// Smoke test of the packaged application (release/win-unpacked/Mesh-to-CAD.exe), run by
// the release workflow with M2C_APP_BINARY. It checks what only the installer build can
// get wrong: the bundled kernel starts, the example scans and licences are installed,
// and the renderer is sandboxed.

import { expect, test } from '@playwright/test';

import { launchApp } from './support/app';

test.skip(!process.env.M2C_APP_BINARY, 'set M2C_APP_BINARY to the packaged Mesh-to-CAD.exe');

test('the packaged app starts its kernel and opens the bundled example', async () => {
  const { app, page } = await launchApp();
  try {
    const packaged = await app.evaluate(({ app: electronApp }) => electronApp.isPackaged);
    expect(packaged).toBe(true);
    const sandboxed = await app.evaluate(({ app: electronApp }) =>
      electronApp
        .getAppMetrics()
        .filter((metric) => metric.type === 'Tab')
        .every((metric) => metric.sandboxed === true),
    );
    expect(sandboxed).toBe(true);

    const installed = await app.evaluate(async () => {
      const { existsSync } = await import('node:fs');
      const { join } = await import('node:path');
      const resources = process.resourcesPath;
      return [
        'kernel/m2c-kernel.exe',
        'examples/bracket.stl',
        'help/de/index.html',
        'help/en/getting-started.html',
        'licenses/INDEX.txt',
        'licenses/occt/LGPL-2.1.txt',
      ].filter((file) => !existsSync(join(resources, file)));
    });
    expect(installed).toEqual([]);

    await expect(page.getByTestId('empty-open-example')).toBeEnabled();
    await page.getByTestId('empty-open-example').click();
    await expect(page.getByTestId('panel-import-mesh')).toBeVisible();
    await page.getByTestId('panel-ok').click();
    await expect(page.getByTestId('tree-node-scan')).toBeVisible();
    await page.evaluate(() => window.__m2cTest?.waitForIdle(60_000));
    expect(await page.evaluate(() => window.__m2cTest?.scene().scanFaces)).toBeGreaterThan(100_000);

    await page.getByTestId('menu-help').click();
    await page.getByTestId('menu-item-help.about').click();
    await expect(page.getByTestId('about-versions')).toContainText('8.');
    await page.screenshot({ path: 'test-results/packaged-example.png' });
  } finally {
    await app.close();
  }
});
