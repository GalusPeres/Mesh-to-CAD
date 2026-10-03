// User test of the freeform net built by hand, the QuickSurface way
// (docs/research/quicksurface.md): a face by four clicks, rows by the D grip and by
// Alt drag, a plain drag moves, a docked face, a rectangle by two clicks, a bridge,
// more resolution, and OK makes a surface feature. All on the free part of the plate.

import { PART } from './part.mjs';

const TOP = PART.plate[2];
const RIGHT = PART.plate[0];

/** Border edges that are on screen. */
async function border(d) {
  const info = await d.toolInfo();
  return (info?.border ?? []).filter((edge) => edge.screen);
}

/** The border edge whose middle scores highest. */
async function edgeWhere(d, score) {
  const edges = await border(d);
  return edges.reduce((best, edge) => (score(edge.middle) > score(best.middle) ? edge : best));
}

const quads = async (d) => (await d.toolInfo())?.quads ?? 0;
const points = async (d) => (await d.toolInfo())?.points ?? 0;

export async function netTest(d) {
  await d.press('stage-model');
  await d.press('tool-freeform-net');
  await d.command('view.iso');
  await d.command('view.fitAll');
  const state = (await d.toolInfo())?.state;
  d.check('an empty net starts placing a face', state?.facing && state.faceMode === 'quad');

  // 1. A face by four clicks on the plate's top.
  for (const [x, y] of [
    [62, 15],
    [72, 15],
    [72, 25],
    [62, 25],
  ])
    await d.tap(await d.at([x, y, TOP]));
  await d.settle();
  d.check('four clicks give a face', (await quads(d)) === 1 && (await points(d)) === 4);
  await d.shot('net-1-face');

  // 2. The D grip of the edge towards the right wall, dragged over the rim onto the wall.
  let edge = await edgeWhere(d, (m) => m[0]);
  await d.hover(edge.screen);
  edge = await edgeWhere(d, (m) => m[0]);
  await d.drag(edge.handle, await d.at([RIGHT, 20, TOP - 4]));
  await d.settle();
  const wall = await edgeWhere(d, (m) => -m[2]);
  d.check('the D grip adds a row', (await quads(d)) === 2, `${await quads(d)} quads`);
  d.check(
    'the row stays on the wall where it was dropped (#3)',
    Math.abs(wall.middle[0] - RIGHT) < 0.5,
    wall.middle.join(', '),
  );
  await d.shot('net-2-row');

  // 3. A plain drag of that edge moves it; Alt drag adds the next row down the wall.
  await d.drag(wall.screen, { x: wall.screen.x + 3, y: wall.screen.y + 12 }, {}, 8);
  await d.settle();
  d.check('a plain edge drag moves', (await quads(d)) === 2, `${await quads(d)} quads`);
  const moved = await edgeWhere(d, (m) => -m[2]);
  await d.drag(moved.screen, await d.at([RIGHT, 20, 1.5]), { alt: true });
  await d.settle();
  d.check('Alt drag adds a row', (await quads(d)) === 3, `${await quads(d)} quads`);
  await d.shot('net-3-alt');

  // 4. A second face whose first and last corners land near the first face's left
  // corners: it docks there and shares them.
  const before = await points(d);
  await d.press('freeform-net-add-face');
  for (const [x, y] of [
    [62.4, 15.3],
    [54, 15],
    [54, 25],
    [62.3, 24.6],
  ]) {
    await d.tap(await d.at([x, y, TOP]));
  }
  await d.settle();
  d.check(
    'a face docks onto the net',
    (await points(d)) === before + 2,
    `${await points(d)} points`,
  );
  await d.shot('net-4-dock');

  // 5. A rectangle by two clicks, beside the net, then bridged to it.
  const pieces = await quads(d);
  await d.press('freeform-net-add-rectangle');
  await d.tap(await d.at([62, 29, TOP]));
  await d.hover(await d.at([72, 37, TOP]));
  await d.shot('net-5-rectangle-preview');
  await d.tap(await d.at([72, 37, TOP]));
  await d.settle();
  d.check(
    'two clicks give a rectangle',
    (await quads(d)) === pieces + 1,
    `${await quads(d)} quads`,
  );
  const near = await edgeWhere(
    d,
    (m) => -Math.abs(m[1] - 25) - Math.abs(m[0] - 67) - Math.abs(m[2] - TOP),
  );
  const far = await edgeWhere(
    d,
    (m) => -Math.abs(m[1] - 29) - Math.abs(m[0] - 67) - Math.abs(m[2] - TOP),
  );
  await d.tap(near.screen);
  await d.tap(far.screen, { shift: true });
  await d.tap(far.screen, { button: 2 });
  await d.shot('net-6-bridge-menu');
  await d.press('freeform-net-bridge');
  await d.settle();
  d.check('a bridge closes the gap', (await quads(d)) === pieces + 2, `${await quads(d)} quads`);

  // 6. More resolution from the right-click menu, then OK: an open surface in the history.
  const coarse = await quads(d);
  await d.tap(await d.at([30, 45, TOP]), { button: 2 });
  await d.press('freeform-net-refine');
  await d.settle();
  d.check('more resolution', (await quads(d)) === coarse * 4, `${await quads(d)} quads`);
  await d.shot('net-7-refined');

  await d.press('panel-ok');
  const snapshot = await d.until(async () => {
    const doc = await d.kernel('doc.get');
    const net = doc.document.features.find((feature) => feature.type === 'freeformNet');
    const status = net && doc.status.features[net.id];
    return status ? { net, status } : null;
  }, 'the net feature');
  const issues = snapshot.status.issues?.map((issue) => issue.code) ?? [];
  d.check('OK keeps an open surface', issues.includes('surfacing.openNet'), snapshot.status.state);
  d.check('the surface is valid', !snapshot.status.error, snapshot.status.error?.code ?? '');
  await d.shot('net-8-surface');
}
