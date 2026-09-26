// Viewport performance on a 2M-face scan (docs/ARCHITECTURE.md 1.5 and 7.6).
// Local only: CI runners have no GPU. Run after `npm run build` with
//   npx playwright test tests/e2e/viewport-perf.spec.ts
// The measured numbers go to test-results/viewport-perf.json for the pull request.

import { mkdirSync, mkdtempSync, openSync, closeSync, writeFileSync, writeSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { ROOT, launchApp, stubOpenDialog } from './support/app';

const AROUND = 1000;
const TUBE = 1000;
const FACES = 2 * AROUND * TUBE;
const INTERACTIVE_BUDGET_MS = 3000;
const LONG_TASK_BUDGET_MS = 100;
const BRUSH_BUDGET_MS = 8;

/**
 * A 2 000 000-triangle torus (R 60, r 20 mm) with a fine ripple, so that
 * neighbouring faces differ like on a scan. Written in slices to keep memory low.
 */
function writeLargeTorus(file: string): void {
  const handle = openSync(file, 'w');
  const header = Buffer.alloc(84);
  header.write('Mesh-to-CAD viewport performance torus', 0, 'ascii');
  header.writeUInt32LE(FACES, 80);
  writeSync(handle, header);
  const point = (i: number, j: number): [number, number, number] => {
    const u = (2 * Math.PI * (i % AROUND)) / AROUND;
    const v = (2 * Math.PI * (j % TUBE)) / TUBE;
    const minor = 20 + 0.05 * Math.sin(37 * u) * Math.cos(23 * v);
    const ring = 60 + minor * Math.cos(v);
    return [ring * Math.cos(u), ring * Math.sin(u), minor * Math.sin(v)];
  };
  for (let i = 0; i < AROUND; i += 1) {
    const slice = Buffer.alloc(TUBE * 2 * 50);
    let offset = 0;
    for (let j = 0; j < TUBE; j += 1) {
      const a = point(i, j);
      const b = point(i + 1, j);
      const c = point(i + 1, j + 1);
      const d = point(i, j + 1);
      for (const triangle of [
        [a, b, c],
        [a, c, d],
      ]) {
        triangle.flat().forEach((value, k) => slice.writeFloatLE(value, offset + 12 + k * 4));
        offset += 50;
      }
    }
    writeSync(handle, slice);
  }
  closeSync(handle);
}

interface PerfState {
  longTasks: { start: number; duration: number }[];
  documentAt: number;
  shownAt: number;
}

declare global {
  interface Window {
    __viewportPerf?: PerfState;
  }
}

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length ? (sorted[Math.floor(sorted.length / 2)] ?? 0) : Number.NaN;
};

test.skip(!!process.env.CI, 'needs a GPU; run locally');

test('a 2M-face scan becomes interactive quickly and brush samples stay fast', async () => {
  test.setTimeout(300_000);
  const stl = path.join(mkdtempSync(path.join(tmpdir(), 'm2c-perf-')), 'torus-2m.stl');
  writeLargeTorus(stl);
  const { app, page } = await launchApp({ gpu: true });
  const report: Record<string, unknown> = { faces: FACES };

  try {
    // Watch long tasks and the moment the scan is completely drawn after the kernel's commit.
    await page.evaluate((faces) => {
      const state: PerfState = { longTasks: [], documentAt: 0, shownAt: 0 };
      window.__viewportPerf = state;
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries())
          state.longTasks.push({ start: entry.startTime, duration: entry.duration });
      }).observe({ type: 'longtask' });
      const poll = () => {
        const hooks = window.__m2cTest;
        if (hooks && !state.documentAt && (hooks.revision() ?? 0) > 0)
          state.documentAt = performance.now();
        if (state.documentAt && hooks?.scene().scanFaces === faces)
          state.shownAt = performance.now();
        if (!state.shownAt) requestAnimationFrame(poll);
      };
      requestAnimationFrame(poll);
    }, FACES);

    await stubOpenDialog(app, stl);
    await page.getByTestId('empty-import').click();
    await expect(page.getByTestId('panel-import-mesh')).toBeVisible();
    await page.getByTestId('panel-ok').click();
    await page.waitForFunction(() => (window.__viewportPerf?.shownAt ?? 0) > 0, undefined, {
      timeout: 240_000,
    });
    // Let the preparation worker finish (topology, BVH) and record what that costs as well.
    await page.waitForTimeout(3000);
    const load = await page.evaluate(() => {
      const state = window.__viewportPerf!;
      const during = state.longTasks.filter(
        (task) => task.start + task.duration >= state.documentAt,
      );
      return {
        interactiveMs: state.shownAt - state.documentAt,
        longestTaskMs: Math.max(0, ...during.map((task) => task.duration)),
        longTasks: during.map((task) => Math.round(task.duration)),
      };
    });
    report.load = load;
    expect.soft(load.interactiveMs).toBeLessThan(INTERACTIVE_BUDGET_MS);
    expect.soft(load.longestTaskMs).toBeLessThan(LONG_TASK_BUDGET_MS);

    // Orbit with the right button and record frame intervals.
    const canvas = page.getByTestId('viewport-canvas');
    const box = await canvas.boundingBox();
    if (!box) throw new Error('viewport canvas not visible');
    const cx = Math.round(box.x + box.width / 2);
    const cy = Math.round(box.y + box.height / 2);
    await page.evaluate(() => {
      const frames: number[] = [];
      (window as unknown as { __frames: number[] }).__frames = frames;
      let last = performance.now();
      const tick = (now: number) => {
        frames.push(now - last);
        last = now;
        if (frames.length < 400) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    await page.mouse.move(cx, cy);
    await page.mouse.down({ button: 'right' });
    for (let step = 1; step <= 120; step += 1) await page.mouse.move(cx + step * 3, cy + step);
    await page.mouse.up({ button: 'right' });
    const frames = await page.evaluate(() =>
      (window as unknown as { __frames: number[] }).__frames.slice(5),
    );
    report.orbit = {
      medianFrameMs: median(frames),
      p95FrameMs: [...frames].sort((a, b) => a - b)[Math.floor(frames.length * 0.95)],
    };

    // Brush samples through the real brush tool, when that tool is available.
    const brush = page.getByTestId('tool-select-brush');
    if ((await brush.count()) > 0 && (await brush.isEnabled())) {
      await brush.click();
      await page.evaluate(() => performance.clearMeasures('viewport.brushSample'));
      await page.mouse.move(cx, cy);
      await page.mouse.down();
      for (let step = 0; step < 90; step += 1) {
        const angle = (step / 90) * 2 * Math.PI;
        await page.mouse.move(
          Math.round(cx + 120 * Math.cos(angle)),
          Math.round(cy + 80 * Math.sin(angle)),
        );
      }
      await page.mouse.up();
      const samples = await page.evaluate(() =>
        performance.getEntriesByName('viewport.brushSample').map((entry) => entry.duration),
      );
      report.brush = { samples: samples.length, medianMs: median(samples) };
      expect(samples.length).toBeGreaterThan(10);
      expect.soft(median(samples)).toBeLessThan(BRUSH_BUDGET_MS);
    } else {
      report.brush = 'brush tool not available in this build';
      test.info().annotations.push({ type: 'note', description: 'brush tool not available' });
    }
    await page.screenshot({ path: 'test-results/viewport-perf.png' });
  } finally {
    mkdirSync(path.join(ROOT, 'test-results'), { recursive: true });
    writeFileSync(
      path.join(ROOT, 'test-results', 'viewport-perf.json'),
      `${JSON.stringify(report, null, 2)}\n`,
    );
    await app.close();
  }
});
