// User test of the issue's own case (#7): a block built straight (a plane on the
// bottom, a sketch where one click fits the outline, an extrusion), then the rounded
// edge the extrusion lacks: a net laid on it by hand, pushed past the block's faces,
// and Zuschneiden cuts the block with it into one body with the rounding.

import { BLOCK, blockVolume } from './block.mjs';

const [LENGTH, DEPTH, HEIGHT] = BLOCK.size;
const R = BLOCK.radius;

const features = async (d, type) =>
  (await d.kernel('doc.get')).document.features.filter((feature) => feature.type === type);

async function newFeature(d, type) {
  return d.until(async () => (await features(d, type)).at(-1)?.id, `the ${type} feature`);
}

/** The block's bottom as a fitted plane, its sketch and its extrusion. */
async function straightBlock(d) {
  const { faces } = await d.kernel('automation.facesInBox', {
    min: [1, 1, -0.5],
    max: [LENGTH - 1, DEPTH - 1, 0.5],
    facing: [0, 0, -1],
    maxAngleDeg: 10,
  });
  await d.select(faces);
  await d.press('tool-fit-primitive');
  await d.pressWhenReady('panel-ok');
  const plane = await newFeature(d, 'fit');
  await d.select([]);

  await d.press(`tree-node-${plane}`);
  await d.command('tool.section-sketch');
  // The bottom plane faces down; the cut goes into the part.
  await d.press('sketch-flip');
  await d.pressWhenReady('panel-ok');
  await d.until(async () => (await d.toolInfo())?.outlines?.length, 'the sketch mode');
  await d.tap((await d.toolInfo()).outlines[0].screen);
  const [shape] = await d.until(async () => (await d.toolInfo())?.shapes, 'the fitted outline');
  await d.settle();
  d.check(
    'one click fits the 60 x 40 outline',
    shape?.sizes?.length === LENGTH && shape?.sizes?.width === DEPTH,
    `${shape?.kind} ${JSON.stringify(shape?.sizes)}`,
  );
  await d.press('panel-ok');
  await newFeature(d, 'sketch');

  await d.press('tool-extrude');
  await d.pressWhenReady('panel-ok');
  const extrude = await newFeature(d, 'extrude');
  const body = await d.until(
    async () => (await d.kernel('doc.get')).status.bodies.find((item) => item.id === extrude),
    'the block',
  );
  d.check(
    'the extrusion is the sharp block',
    Math.abs(body.volume - LENGTH * DEPTH * HEIGHT) < 1,
    `${body.volume.toFixed(1)} mm³`,
  );
  return { plane, body: extrude };
}

/** A face over the rounding by four clicks, finer three times, fitted, pushed past the block. */
async function roundingNet(d) {
  await d.command('view.iso');
  // Turn the view half round to look at the rounded back edge.
  await d.drag({ x: 650, y: 500 }, { x: 650 + Math.PI / 0.008, y: 500 }, { button: 2 }, 20);
  await d.key('Escape');
  await d.command('view.fitAll');
  await d.press('tool-freeform-net');
  const before = DEPTH - R - 2;
  const below = HEIGHT - R - 2;
  for (const point of [
    [1, before, HEIGHT],
    [LENGTH - 1, before, HEIGHT],
    [LENGTH - 1, DEPTH, below],
    [1, DEPTH, below],
  ])
    await d.tap(await d.at(point));
  await d.settle();
  const middle = [LENGTH / 2, DEPTH - R + R * Math.SQRT1_2, HEIGHT - R + R * Math.SQRT1_2];
  for (let i = 0; i < 3; i += 1) {
    await d.tap(await d.at(middle), { button: 2 });
    await d.press('freeform-net-refine');
    await d.settle();
  }
  // The right clicks chose points; Escape clears the choice, so the whole net is fitted.
  await d.key('Escape');
  for (let i = 0; i < 3; i += 1) {
    await d.press('freeform-net-fit');
    await d.settle();
  }
  const fitted = await d.toolInfo();
  const summary = fitted?.state?.summary;
  d.check(
    'the net lies on the rounding',
    fitted?.quads === 64 && summary?.rms < 0.05,
    `${fitted?.quads} quads, RMS ${summary?.rms?.toFixed(3)} mm, max ${summary?.max?.toFixed(3)} mm`,
  );
  await d.shot('rounding-1-net');

  await d.press('freeform-net-push');
  await d.settle();
  const pushed = await d.toolInfo();
  const border = (pushed?.border ?? []).map((edge) => edge.middle);
  const past = border.every(
    ([x, y, z]) => x < 0 || x > LENGTH || y > DEPTH + 0.3 || z > HEIGHT + 0.3,
  );
  d.check(
    'its border is pushed past the top, the back and both ends',
    pushed?.state?.pushed?.moved > 0 && past,
    `${pushed?.state?.pushed?.moved} points`,
  );
  await d.shot('rounding-2-pushed');
  await d.press('panel-ok');
  return newFeature(d, 'freeformNet');
}

async function previewed(d) {
  await d.pause(500);
  return d.until(async () => {
    const info = await d.toolInfo();
    return info?.preview === 'ok' || info?.preview === 'error' ? info : null;
  }, 'the trim preview');
}

export async function roundingTest(d) {
  await d.press('stage-model');
  const { plane, body } = await straightBlock(d);
  const net = await roundingNet(d);

  // Zuschneiden with the block and the net; the tree still has the plane chosen.
  await d.press('tool-trim-solid');
  const start = (await d.toolInfo()).inputs;
  if (start.planes.includes(plane)) await d.press(`trim-solid-planes-${plane}`);
  if (!start.surfaces.includes(net)) await d.press(`trim-solid-surfaces-${net}`);
  if (!start.bodies.includes(body)) await d.press(`trim-solid-bodies-${body}`);
  const trimmed = await previewed(d);
  d.check(
    'the net cuts the corner off the block',
    trimmed.canCommit && trimmed.stats?.pieces === 2 && trimmed.stats?.kept === 1,
    `${trimmed.error ?? trimmed.state}, ${trimmed.stats?.pieces} pieces`,
  );
  await d.shot('rounding-3-trim');
  await d.pressWhenReady('panel-ok');

  const doc = await d.until(async () => {
    const current = await d.kernel('doc.get');
    const trim = current.document.features.find((feature) => feature.type === 'trimSolid');
    return trim && current.status.features[trim.id] ? current : null;
  }, 'the trim feature');
  const result = doc.status.bodies.find((item) => item.id === body);
  d.check('Zuschneiden makes one body', result?.solids === 1, `${doc.status.bodies.length}`);
  const removed = LENGTH * DEPTH * HEIGHT - blockVolume();
  const error = result ? (result.volume - blockVolume()) / removed : 1;
  d.check(
    'the corner it removed is the rounding’s',
    Math.abs(error) < 0.1,
    `${result?.volume.toFixed(1)} mm³ vs ${blockVolume().toFixed(1)} mm³ (${(error * 100).toFixed(1)} % of the corner)`,
  );
  const { stats } = await d.kernel('inspection.deviation', { bodies: [body], maxDistance: 2 });
  d.check(
    'it lies on the scan',
    stats.rms !== null && stats.rms < 0.05 && Math.max(stats.max, -stats.min) < 0.3,
    `RMS ${stats.rms?.toFixed(3)} mm, max ${stats.max?.toFixed(3)} / ${stats.min?.toFixed(3)} mm, ${(100 * (stats.within ?? 0)).toFixed(1)} % within tolerance`,
  );
  const preflight = await d.kernel('export.preflight', { bodies: [] });
  const check = preflight.bodies.find((item) => item.body === body);
  d.check(
    'it exports as one closed solid',
    check && check.closed && check.valid && !check.blocking,
    JSON.stringify(check?.problems ?? []),
  );
  await d.shot('rounding-4-body');
}
