// User test of the section sketch, the QuickSurface way (docs/research/quicksurface.md,
// 2D sketch): a plane fitted to the plate's top, selected before the tool opens, cut
// just above the face; an empty sketch, one click inside the boss outline fits the
// circle with its design value, and OK makes the sketch feature.

import { PART } from './part.mjs';

const TOP = PART.plate[2];
const { centre, radius } = PART.boss;

/** A plane fitted to the free part of the plate's top, as Fit primitive would add it. */
async function topPlane(d) {
  const { faces } = await d.kernel('automation.facesInBox', {
    min: [45, 5, TOP - 0.5],
    max: [75, 45, TOP + 0.5],
    facing: [0, 0, 1],
    maxAngleDeg: 10,
  });
  const { revision } = await d.kernel('doc.get');
  const params = { faces: { $typed: 'uint32', values: faces }, kind: 'plane', robust: false };
  await d.kernel('doc.apply', {
    baseRevision: revision,
    ops: [{ type: 'addFeature', feature: { type: 'fit', params } }],
    label: 'fit',
  });
  const { document } = await d.kernel('doc.get');
  return document.features.find((feature) => feature.type === 'fit').id;
}

export async function sketchTest(d) {
  const plane = await topPlane(d);
  await d.press(`tree-node-${plane}`);
  await d.command('tool.section-sketch');
  await d.command('view.top');
  await d.shot('sketch-1-plane');
  await d.press('sketch-fit-all');
  await d.press('panel-ok');
  await d.until(async () => (await d.toolInfo())?.outlines?.length, 'the sketch mode');

  const info = await d.toolInfo();
  d.check('the cut above the top meets only the boss', info.outlines.length === 1);
  const boss = info.outlines[0];
  d.check(
    'the outline lies on the boss',
    Math.hypot(boss.at[0] - centre[0], boss.at[1] - centre[1]) < radius,
    boss.at.map((v) => v.toFixed(2)).join(', '),
  );
  await d.hover(boss.screen);
  await d.shot('sketch-2-hover');
  await d.tap(boss.screen);
  const shapes = await d.until(
    async () => (await d.toolInfo())?.shapes?.length && (await d.toolInfo()).shapes,
    'the fitted shape',
  );
  await d.settle();
  const [circle] = shapes;
  d.check('one click fits a circle', shapes.length === 1 && circle.kind === 'circle', circle?.kind);
  d.check(
    'its diameter is the design value 20 mm',
    Math.abs((circle?.sizes?.diameter ?? 0) - 2 * radius) < 1e-6,
    `${circle?.sizes?.diameter}`,
  );
  await d.shot('sketch-3-circle');

  await d.press('panel-ok');
  const { document } = await d.until(async () => {
    const snapshot = await d.kernel('doc.get');
    return snapshot.document.features.some((f) => f.type === 'sketch') && snapshot;
  }, 'the sketch feature');
  const sketch = document.features.find((feature) => feature.type === 'sketch');
  d.check('OK adds the sketch with one circle', sketch.params.entities.length === 1);
  await d.shot('sketch-4-done');
}
