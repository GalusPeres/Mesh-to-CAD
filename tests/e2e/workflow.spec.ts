// The v0.1 workflow end to end (docs/ARCHITECTURE.md 7.6): import, align, segment, fit,
// sketch, extrude, fillet, deviation and STEP export, plus the project tree edits.
// Selectors are test ids and ARIA roles; viewport input goes through the test hooks.
// Steps whose tools are not ready yet are marked test.fixme and are enabled as the
// packages merge; the steps share one application instance and run in order.

import { existsSync, mkdtempSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { type ElectronApplication, expect, type Page, test } from '@playwright/test';

import { launchApp, stubOpenDialog } from './support/app';

const BOX = { x: 100, y: 70, z: 20 };
const STEP_MM = 2;

/**
 * A closed box of 100 x 70 x 20 mm with every side meshed as a grid of 2 mm squares,
 * written as binary STL. Returns the face indices of the top side (+Z).
 */
function writeBoxStl(file: string): { faces: number; top: number[] } {
  const triangles: number[][][] = [];
  const top: number[] = [];
  const side = (
    origin: number[],
    u: number[],
    v: number[],
    lengthU: number,
    lengthV: number,
    isTop = false,
  ) => {
    const point = (a: number, b: number) =>
      origin.map((value, axis) => value + u[axis]! * a + v[axis]! * b);
    for (let a = 0; a < lengthU; a += STEP_MM) {
      for (let b = 0; b < lengthV; b += STEP_MM) {
        const p0 = point(a, b);
        const p1 = point(a + STEP_MM, b);
        const p2 = point(a + STEP_MM, b + STEP_MM);
        const p3 = point(a, b + STEP_MM);
        if (isTop) top.push(triangles.length, triangles.length + 1);
        triangles.push([p0, p1, p2], [p0, p2, p3]);
      }
    }
  };
  // Each side is spanned counter-clockwise seen from outside, so normals point outwards.
  side([0, 0, 0], [0, 1, 0], [1, 0, 0], BOX.y, BOX.x);
  side([0, 0, BOX.z], [1, 0, 0], [0, 1, 0], BOX.x, BOX.y, true);
  side([0, 0, 0], [1, 0, 0], [0, 0, 1], BOX.x, BOX.z);
  side([0, BOX.y, 0], [0, 0, 1], [1, 0, 0], BOX.z, BOX.x);
  side([0, 0, 0], [0, 0, 1], [0, 1, 0], BOX.z, BOX.y);
  side([BOX.x, 0, 0], [0, 1, 0], [0, 0, 1], BOX.y, BOX.z);

  const buffer = Buffer.alloc(84 + triangles.length * 50);
  buffer.write('Mesh-to-CAD end-to-end workflow box', 0, 'ascii');
  buffer.writeUInt32LE(triangles.length, 80);
  triangles.forEach((triangle, index) => {
    const offset = 84 + index * 50 + 12;
    triangle
      .flat()
      .forEach((value, component) => buffer.writeFloatLE(value, offset + component * 4));
  });
  writeFileSync(file, buffer);
  return { faces: triangles.length, top };
}

async function stubSaveDialog(app: ElectronApplication, file: string): Promise<void> {
  await app.evaluate(({ dialog }, chosen) => {
    dialog.showSaveDialog = () => Promise.resolve({ canceled: false, filePath: chosen });
  }, file);
}

async function idle(page: Page): Promise<void> {
  await page.evaluate(() => window.__m2cTest?.waitForIdle());
}

async function revision(page: Page): Promise<number> {
  return (await page.evaluate(() => window.__m2cTest?.revision())) ?? -1;
}

/** Commit the open panel and wait for the new revision. */
async function commitPanel(page: Page): Promise<void> {
  const before = await revision(page);
  await page.getByTestId('panel-ok').click();
  await expect.poll(() => revision(page)).toBeGreaterThan(before);
  await idle(page);
}

test.describe.configure({ mode: 'serial' });

let app: ElectronApplication;
let page: Page;
let work: string;
let box: { faces: number; top: number[] };

test.beforeAll(async () => {
  work = mkdtempSync(path.join(tmpdir(), 'm2c-workflow-'));
  box = writeBoxStl(path.join(work, 'box.stl'));
  ({ app, page } = await launchApp());
});

test.afterAll(async () => {
  await app?.close();
});

test('imports the scan and shows it in the tree', async () => {
  await expect(page.getByTestId('empty-state')).toBeVisible();
  await stubOpenDialog(app, path.join(work, 'box.stl'));
  await page.getByTestId('empty-import').click();
  await expect(page.getByTestId('panel-import-mesh')).toBeVisible();
  await commitPanel(page);
  await expect(page.getByTestId('tree-node-scan')).toBeVisible();
  expect(await page.evaluate(() => window.__m2cTest?.scene().scanFaces)).toBe(box.faces);
  await page.getByTestId('tree-node-scan').click();
  await expect(page.getByTestId('properties-title')).toHaveText('Scan');
});

test('aligns the scan automatically', async () => {
  await page.getByTestId('stage-align').click();
  await page.getByTestId('tool-align-auto').click();
  await expect(page.getByTestId('panel-align-auto')).toBeVisible();
  await commitPanel(page);
  await expect(page.getByTestId('tree-node-alignment')).toBeVisible();
});

test('segments the scan into regions', async () => {
  await page.getByTestId('stage-model').click();
  await page.getByTestId('tool-segment').click();
  await expect(page.getByTestId('panel-segment')).toBeVisible();
  // The preview runs on its own; OK is enabled once it has found regions.
  await expect(page.getByTestId('panel-ok')).toBeEnabled({ timeout: 60_000 });
  await commitPanel(page);
  await expect(page.getByTestId('tree-group-regions')).toBeVisible();
});

test('fits a plane to the top face and edits it from the tree', async () => {
  await page.getByTestId('stage-model').click();
  await page.evaluate((faces) => window.__m2cTest?.selectFaces(faces), box.top);
  await page.getByTestId('tool-fit-primitive').click();
  await expect(page.getByTestId('panel-fit-primitive')).toBeVisible();
  await commitPanel(page);

  const fit = firstFeatureRow(page);
  await expect(fit).toBeVisible();
  const fitId = (await fit.getAttribute('data-testid'))!.replace('tree-node-', '');

  // Rename with F2 in the tree; one revision, undoable.
  await fit.click();
  await page.keyboard.press('F2');
  await page.getByTestId('rename-name').fill('Deckfläche');
  await commitRename(page);
  await expect(page.getByTestId(`tree-node-${fitId}`)).toContainText('Deckfläche');
  await page.keyboard.press('Control+z');
  await expect(page.getByTestId(`tree-node-${fitId}`)).not.toContainText('Deckfläche');

  // Suppress and restore through the context menu.
  await page.getByTestId(`tree-node-${fitId}`).click({ button: 'right' });
  await page.getByTestId('tree-menu-suppress').click();
  await expect(page.getByTestId('properties-feature-state')).toHaveAttribute(
    'data-state',
    'suppressed',
  );
  await page.getByTestId(`tree-node-${fitId}`).click({ button: 'right' });
  await page.getByTestId('tree-menu-unsuppress').click();
  await expect(page.getByTestId('properties-feature-state')).toHaveAttribute('data-state', 'ok');

  // Double-click opens the edit tool; Esc leaves it without changes.
  await page.getByTestId(`tree-node-${fitId}`).dblclick();
  await expect(page.getByTestId('panel-fit-primitive')).toBeVisible();
  await page.getByTestId('panel-cancel').click();
});

/** History rows of features have the test id `tree-node-f<n>` (bodies use `tree-node-body-`). */
function firstFeatureRow(page: Page) {
  return page.locator('[role="treeitem"][data-testid^="tree-node-f"]').first();
}

async function commitRename(page: Page): Promise<void> {
  const before = await revision(page);
  await page.getByTestId('rename-ok').click();
  await expect.poll(() => revision(page)).toBeGreaterThan(before);
}

test.fixme('sketches the side profile', async () => {
  await page.getByTestId('tool-section-sketch').click();
  await commitPanel(page);
});

test.fixme('extrudes the sketch into a body', async () => {
  await page.getByTestId('tool-extrude').click();
  await commitPanel(page);
  await expect(page.getByTestId('tree-group-bodies')).toBeVisible();
});

test.fixme('rounds an edge of the body', async () => {
  await page.getByTestId('tool-fillet').click();
  await page.evaluate(() => window.__m2cTest?.waitForIdle());
  await commitPanel(page);
});

test.fixme('shows the deviation of the scan from the body', async () => {
  await page.getByTestId('stage-inspect').click();
  await page.getByTestId('tool-deviation').click();
  await commitPanel(page);
});

test.fixme('exports the body as STEP', async () => {
  const file = path.join(work, 'box.step');
  await stubSaveDialog(app, file);
  await page.getByTestId('tool-export-step').click();
  await page.getByTestId('panel-ok').click();
  await expect.poll(() => existsSync(file)).toBe(true);
  expect(statSync(file).size).toBeGreaterThan(1000);
});

test('deletes the fit and undoes the deletion', async () => {
  const fit = firstFeatureRow(page);
  const fitTestId = (await fit.getAttribute('data-testid'))!;
  await fit.click();
  const before = await revision(page);
  await page.keyboard.press('Delete');
  await expect.poll(() => revision(page)).toBeGreaterThan(before);
  await expect(page.getByTestId(fitTestId)).toHaveCount(0);
  await page.keyboard.press('Control+z');
  await expect(page.getByTestId(fitTestId)).toBeVisible();
});

test('opens settings, shortcut help and the about dialog', async () => {
  await page.keyboard.press('Control+,');
  await expect(page.getByTestId('settings-language')).toBeVisible();
  await page.getByTestId('settings-language').selectOption('en');
  await expect(page.getByTestId('menu-file')).toHaveText('File');
  await page.getByTestId('settings-language').selectOption('de');
  await expect(page.getByTestId('menu-file')).toHaveText('Datei');
  await page.getByTestId('settings-close').click();

  await page.getByTestId('tree-node-scan').click();
  await page.keyboard.press('Control+/');
  await expect(page.getByTestId('shortcuts-file')).toBeVisible();
  await page.getByTestId('shortcuts-close').click();

  await page.getByTestId('menu-help').click();
  await page.getByTestId('menu-item-help.about').click();
  await expect(page.getByTestId('about-versions')).toContainText('8.');
  await expect(page.getByTestId('about-log-folder')).toContainText('logs');
  await page.getByTestId('about-close').click();
});
