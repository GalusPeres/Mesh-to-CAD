// User test of the loft up to planes (#22) on a rounded block whose top edge is rounded
// by 2 mm: the loft follows the walls and reaches the bottom (XY) and a plane fitted to
// the top, past the rounding of the scan; the panel shows both planes; the fillet tool
// rounds the top edge picked in the view with its default 2 mm, which is the block's.
//
// The loft is added as an operation: the automation cannot choose an entry of a select
// field yet, so the panel is checked by opening the loft for editing.

import { ROUNDED, roundedBlockVolume } from './rounded.mjs';

const [LENGTH, WIDTH, HEIGHT] = ROUNDED.size;

async function addFeature(d, feature, label) {
  const { revision } = await d.kernel('doc.get');
  await d.kernel('doc.apply', {
    baseRevision: revision,
    ops: [{ type: 'addFeature', feature }],
    label,
  });
  const { document } = await d.kernel('doc.get');
  return document.features.at(-1).id;
}

/** A plane fitted to the flat part of the top, as Form einpassen adds it. */
async function topPlane(d) {
  const inset = ROUNDED.top + 1;
  const { faces } = await d.kernel('automation.facesInBox', {
    min: [inset, inset, HEIGHT - 0.2],
    max: [LENGTH - inset, WIDTH - inset, HEIGHT + 0.2],
    facing: [0, 0, 1],
    maxAngleDeg: 5,
  });
  const params = { faces: { $typed: 'uint32', values: faces }, kind: 'plane', robust: false };
  return addFeature(d, { type: 'fit', params }, 'fit');
}

async function bodyOf(d, owner) {
  const doc = await d.kernel('doc.get');
  return { doc, body: doc.status.bodies.find((item) => item.owner === owner) };
}

export async function loftEndTest(d) {
  await d.press('stage-model');
  const top = await topPlane(d);
  const axis = await d.kernel('freeform.loftAxis', { path: 'Z' });
  d.check(
    'the default range lies inside the block',
    axis.start > 0 && axis.end < HEIGHT,
    `${axis.start.toFixed(2)} … ${axis.end.toFixed(2)} mm`,
  );
  const loft = await addFeature(
    d,
    {
      type: 'loft',
      params: {
        ...{ path: 'Z', start: axis.start, end: axis.end, sectionCount: 12, faces: null },
        ...{ operation: 'newBody', targetBody: null, startPlane: 'XY', endPlane: top },
      },
    },
    'loft',
  );
  let { doc, body } = await bodyOf(d, loft);
  d.check('the loft is a valid solid', body?.valid && doc.status.features[loft].state === 'ok');
  const prism = (LENGTH * WIDTH - (4 - Math.PI) * ROUNDED.corner ** 2) * HEIGHT;
  const off = Math.abs(body.volume - prism) / prism;
  d.check(
    'it reaches both planes: the full block without its rounding',
    off < 0.002,
    `${(off * 100).toFixed(3)} % off`,
  );

  await d.command('view.iso');
  await d.command('view.fitAll');
  await d.press(`tree-node-${loft}`);
  await d.press('properties-edit');
  await d.until(async () => (await d.state())?.activeTool === 'loft', 'the loft panel');
  await d.shot('loftend-1-panel');
  await d.key('Escape');

  await d.press('tool-fillet');
  await d.tap(await d.at([LENGTH / 2, 0, HEIGHT]));
  await d.until(
    async () => {
      await d.press('panel-ok').catch(() => undefined);
      return (await d.kernel('doc.get')).document.features.some((item) => item.type === 'fillet');
    },
    'the fillet',
    60_000,
  );
  ({ doc, body } = await bodyOf(d, (await d.kernel('doc.get')).document.features.at(-1).id));
  const fillet = doc.document.features.at(-1);
  d.check(
    'the fillet is built',
    doc.status.features[fillet.id].state === 'ok',
    doc.status.features[fillet.id].state,
  );
  d.check(
    'with the default radius',
    fillet.params.size === ROUNDED.top,
    `${fillet.params.size} mm`,
  );
  const truth = roundedBlockVolume();
  const error = Math.abs(body.volume - truth) / truth;
  d.check(
    'the body is the block with its rounding',
    error < 0.001,
    `${(error * 100).toFixed(3)} % off`,
  );

  const deviation = await d.kernel('inspection.deviation', { bodies: [], maxDistance: 2 });
  const { stats } = deviation;
  d.check(
    'the scan lies on the body',
    stats.within > 0.99 && stats.p99Abs < 0.05,
    `${(stats.within * 100).toFixed(1)} % in ±${stats.tolerance} mm, P99 ${stats.p99Abs.toFixed(3)} mm, max ${Math.max(stats.max, -stats.min).toFixed(3)} mm`,
  );
  await d.key(' ');
  await d.key(' ');
  await d.command('view.iso');
  await d.command('view.fitAll');
  await d.shot('loftend-2-rounded');
}
