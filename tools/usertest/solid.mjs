// User test of finishing a solid from a net, the QuickSurface way (docs/research/
// quicksurface.md, workflow step 7): planes fitted to the tub's bottom and top, an auto
// net over its curved walls, the net pushed past the planes, then Zuschneiden makes
// one body of net and planes. The body must match the tub and export as one solid.

import { TUB, tubVolume } from './tub.mjs';

const [CX, CY] = TUB.centre;
const H = TUB.height;
const ALL = { min: [-1, -1, -1], max: [81, 51, H + 1] };

async function facesIn(d, region, facing = null) {
  const { faces } = await d.kernel('automation.facesInBox', { ...region, facing, maxAngleDeg: 30 });
  return faces;
}

/** The walls: every triangle but those of the top and the bottom, up to the rims. */
async function walls(d) {
  const caps = new Set([
    ...(await facesIn(d, ALL, [0, 0, 1])),
    ...(await facesIn(d, ALL, [0, 0, -1])),
  ]);
  return (await facesIn(d, ALL)).filter((face) => !caps.has(face));
}

const features = async (d, type) =>
  (await d.kernel('doc.get')).document.features.filter((feature) => feature.type === type);

/** Fit a plane to the scan triangles at height z facing `up` (+1) or down (-1). */
async function fitPlane(d, z, up) {
  const before = (await features(d, 'fit')).length;
  await d.select(await facesIn(d, { min: [0, 0, z - 0.2], max: [80, 50, z + 0.2] }, [0, 0, up]));
  await d.press('tool-fit-primitive');
  await d.pressWhenReady('panel-ok');
  const fits = await d.until(async () => {
    const all = await features(d, 'fit');
    return all.length > before ? all : null;
  }, 'the fitted plane');
  return fits.at(-1).id;
}

/** The trim tool's preview once it is computed. */
async function previewed(d) {
  await d.pause(500);
  return d.until(async () => {
    const info = await d.toolInfo();
    return info?.preview === 'ok' || info?.preview === 'error' ? info : null;
  }, 'the trim preview');
}

export async function solidTest(d) {
  await d.press('stage-model');
  await d.command('view.iso');
  await d.command('view.fitAll');
  const bottom = await fitPlane(d, 0, -1);
  const top = await fitPlane(d, H, 1);
  d.check('planes on the bottom and the top', bottom && top, `${bottom}, ${top}`);

  // An auto net over the walls only: a band, open at the top and the bottom.
  await d.select(await walls(d));
  await d.press('tool-freeform-net');
  await d.key('Escape');
  await d.press('Auswahl');
  await d.press('Grob');
  await d.press('freeform-net-generate');
  await d.settle(300_000);
  const net = await d.toolInfo();
  const border = (net?.border ?? []).map((edge) => edge.middle[2]);
  d.check(
    'the net is a band along the walls',
    net?.quads > 50 && border.every((z) => z < 2 || z > H - 2),
    `${net?.quads} quads, border at z ${Math.min(...border).toFixed(2)} … ${Math.max(...border).toFixed(2)}`,
  );
  await d.shot('solid-1-band');

  // Push its border 0.5 mm past the two planes it ends at.
  await d.press('freeform-net-push');
  await d.settle();
  const pushed = await d.toolInfo();
  const heights = (pushed?.border ?? []).map((edge) => edge.middle[2]);
  d.check(
    'the border is pushed past both planes',
    pushed?.state?.pushed?.faces === 2 && heights.every((z) => z < -0.3 || z > H + 0.3),
    `${pushed?.state?.pushed?.moved} points, z ${Math.min(...heights).toFixed(2)} … ${Math.max(...heights).toFixed(2)}`,
  );
  await d.shot('solid-2-pushed');
  await d.press('panel-ok');
  await d.until(async () => (await features(d, 'freeformNet')).length > 0, 'the net feature');

  // Zuschneiden: the net (chosen already, it is the newest surface) and the two planes.
  await d.select([]);
  await d.press('tool-trim-solid');
  await d.press(`trim-solid-planes-${bottom}`);
  await d.press(`trim-solid-planes-${top}`);
  const trimmed = await previewed(d);
  d.check(
    'net and planes enclose one piece',
    trimmed.canCommit && trimmed.stats?.pieces === 1,
    `${trimmed.error ?? trimmed.state}, ${trimmed.stats?.pieces} pieces`,
  );
  await d.shot('solid-3-trim');
  // A click on the body removes the only piece: nothing is left, so no OK; Automatic
  // brings it back.
  await d.tap(await d.at([CX, CY, H]));
  const removed = await previewed(d);
  d.check(
    'a click removes the piece',
    removed.pieces.length === 1 && removed.error === 'cad.noPieceKept' && !removed.canCommit,
    removed.error ?? '',
  );
  await d.shot('solid-4-removed');
  await d.press('trim-solid-automatic');
  await previewed(d);
  await d.pressWhenReady('panel-ok');

  const doc = await d.until(async () => {
    const current = await d.kernel('doc.get');
    const trim = current.document.features.find((feature) => feature.type === 'trimSolid');
    return trim && current.status.features[trim.id] ? { current, trim } : null;
  }, 'the trim feature');
  const status = doc.current.status.features[doc.trim.id];
  const body = doc.current.status.bodies.find((item) => item.id === doc.trim.id);
  d.check('Zuschneiden makes one body', status.state === 'ok' && body?.solids === 1, status.state);
  const expected = tubVolume();
  const error = body ? (body.volume - expected) / expected : 1;
  d.check(
    'its volume is the tub’s',
    Math.abs(error) < 0.01,
    `${body?.volume.toFixed(0)} mm³ vs ${expected.toFixed(0)} mm³ (${(error * 100).toFixed(2)} %)`,
  );
  const deviation = await d.kernel('inspection.deviation', {
    bodies: [doc.trim.id],
    maxDistance: 2,
  });
  const { stats } = deviation;
  d.check(
    'it lies on the scan',
    stats.rms !== null && stats.rms < 0.1,
    `RMS ${stats.rms?.toFixed(3)} mm, ${(100 * (stats.within ?? 0)).toFixed(1)} % within tolerance`,
  );
  const preflight = await d.kernel('export.preflight', { bodies: [] });
  const check = preflight.bodies.find((item) => item.body === doc.trim.id);
  d.check(
    'it exports as one closed solid',
    check && check.closed && check.valid && !check.blocking,
    JSON.stringify(check?.problems ?? []),
  );
  await d.command('view.iso');
  await d.shot('solid-5-body');
}
