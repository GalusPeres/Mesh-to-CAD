import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { type ElectronApplication, type Page, expect, test } from '@playwright/test';

import { launchApp, stubOpenDialog } from './support/app';
import { writeTorusStl } from './support/meshes';

/** Make the next native save dialog return `file` without showing a dialog. */
async function stubSaveDialog(app: ElectronApplication, file: string): Promise<void> {
  await app.evaluate(({ dialog }, chosen) => {
    dialog.showSaveDialog = () => Promise.resolve({ canceled: false, filePath: chosen });
  }, file);
}

async function windowTitle(app: ElectronApplication): Promise<string> {
  return app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.getTitle() ?? '');
}

/** Test id and text of every visible tree row, in order. */
async function treeRows(page: Page): Promise<string[]> {
  return page
    .getByRole('treeitem')
    .evaluateAll((rows) =>
      rows.map((row) => `${row.getAttribute('data-testid') ?? ''}|${row.textContent ?? ''}`),
    );
}

async function importScan(app: ElectronApplication, page: Page, file: string): Promise<void> {
  await stubOpenDialog(app, file);
  await page.getByTestId('empty-import').click();
  await expect(page.getByTestId('panel-import-mesh')).toBeVisible();
  await page.getByTestId('panel-ok').click();
  await expect(page.getByTestId('status-faces')).toHaveText('50.000 Dreiecke');
  await page.evaluate(() => window.__m2cTest?.waitForIdle());
}

test('saves a project, starts a new one and opens the saved project again', async () => {
  const folder = mkdtempSync(path.join(tmpdir(), 'm2c-project-'));
  const stl = path.join(folder, 'torus.stl');
  const project = path.join(folder, 'torus.m2c');
  const faces = writeTorusStl(stl);
  const { app, page } = await launchApp();

  try {
    await importScan(app, page, stl);
    await expect.poll(() => windowTitle(app)).toBe('torus* - Mesh-to-CAD');
    const rowsBefore = await treeRows(page);
    expect(rowsBefore.length).toBeGreaterThan(0);

    await stubSaveDialog(app, project);
    await page.keyboard.press('Control+s');
    await expect(page.getByTestId('status-message')).toHaveText('Gespeichert: torus.m2c');
    expect(existsSync(project)).toBe(true);
    await expect.poll(() => windowTitle(app)).toBe('torus - Mesh-to-CAD');

    await page.keyboard.press('Control+n');
    await expect(page.getByTestId('empty-import')).toBeVisible();
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    expect(await page.evaluate(() => window.__m2cTest?.scene().scanFaces)).toBe(0);
    await expect.poll(() => windowTitle(app)).toBe('Mesh-to-CAD');

    await stubOpenDialog(app, project);
    await page.keyboard.press('Control+o');
    await expect(page.getByTestId('status-faces')).toHaveText('50.000 Dreiecke');
    await page.evaluate(() => window.__m2cTest?.waitForIdle());
    expect(await page.evaluate(() => window.__m2cTest?.scene().scanFaces)).toBe(faces);
    expect(await treeRows(page)).toEqual(rowsBefore);
    await expect.poll(() => windowTitle(app)).toBe('torus - Mesh-to-CAD');

    // Opening a project clears the undo history: there is nothing to undo into.
    await page.getByTestId('viewport-canvas').click({ button: 'middle' });
    await page.keyboard.press('Control+z');
    await expect(page.getByTestId('status-faces')).toHaveText('50.000 Dreiecke');
    await page.screenshot({ path: 'test-results/project-reopened.png' });
  } finally {
    await app.close();
  }
});

test('asks before unsaved changes are replaced by a new project', async () => {
  const folder = mkdtempSync(path.join(tmpdir(), 'm2c-unsaved-'));
  const stl = path.join(folder, 'torus.stl');
  writeTorusStl(stl);
  const { app, page } = await launchApp();

  try {
    await importScan(app, page, stl);
    await page.keyboard.press('Control+n');
    await expect(page.getByRole('dialog')).toContainText('Die Änderungen an torus');
    await page.getByTestId('unsaved-cancel').click();
    await expect(page.getByTestId('status-faces')).toHaveText('50.000 Dreiecke');

    await page.keyboard.press('Control+n');
    await page.getByTestId('unsaved-discard').click();
    await expect(page.getByTestId('empty-import')).toBeVisible();
  } finally {
    await app.close();
  }
});
