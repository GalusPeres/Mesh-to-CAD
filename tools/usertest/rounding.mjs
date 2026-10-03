// User test of rounded and inclined button tops (#24): on the plate built as a body,
// Formen erkennen measures the top edges' rounding (R 0,5 for both round buttons, shown
// and switchable per group) and the inclined top; OK adds the buttons to the plate with
// one fillet for the group and extrudes the inclined button up to a fitted plane. Then,
// built without the rounding, the fillet tool's Radius aus Scan finds the same radius on
// a picked edge. The buttons are compared with the scan face by face.

import { PART } from './part.mjs';
import { ROUNDED } from './roundedPart.mjs';

const DEGREES = 180 / Math.PI;
const TOLERANCE_MM = 0.05;

const near = (value, expected, tolerance) =>
  typeof value === 'number' && Math.abs(value - expected) <= tolerance;

async function recognised(d) {
  return d.until(async () => {
    const info = await d.toolInfo();
    return !info?.state?.job && info?.groups?.length ? info.groups : null;
  }, 'the recognised shapes');
}

/** Open Formen erkennen and return its groups: the round buttons and the inclined one. */
async function recognise(d) {
  await d.press('tool-recognize');
  const groups = await recognised(d);
  return {
    round: groups.find((group) => group.top === 'flat' && group.count === 2),
    inclined: groups.find((group) => group.top === 'inclined'),
  };
}

/** OK in the open panel; returns the features it added once they are there. */
async function build(d) {
  const before = (await d.kernel('doc.get')).document.features.length;
  await d.press('panel-ok');
  const snapshot = await d.until(async () => {
    const current = await d.kernel('doc.get');
    return current.document.features.length > before && !(await d.toolInfo()) ? current : null;
  }, 'the built shapes');
  return { snapshot, added: snapshot.document.features.slice(before) };
}

/** The plate as a body: a sketch of its outline extruded by its height. */
async function plateBody(d) {
  const [length, width, height] = PART.plate;
  const corners = [
    [0, 0],
    [length, 0],
    [length, width],
    [0, width],
  ];
  const add = (type, params) => ({ type: 'addFeature', feature: { type, params } });
  const { revision } = await d.kernel('doc.get');
  await d.kernel('doc.apply', {
    baseRevision: revision,
    label: 'plate',
    ops: [
      add('sketch', {
        section: { type: 'planar', plane: { type: 'standard', plane: 'XY' } },
        points: corners.map(([x, y], i) => ({ id: `p${i}`, x, y })),
        entities: corners.map((_, i) => ({
          type: 'line',
          id: `e${i}`,
          start: `p${i}`,
          end: `p${(i + 1) % 4}`,
        })),
      }),
    ],
  });
  const sketch = (await d.kernel('doc.get')).document.features.at(-1).id;
  const next = await d.kernel('doc.get');
  await d.kernel('doc.apply', {
    baseRevision: next.revision,
    label: 'plate',
    ops: [add('extrude', { sketch, extent: { type: 'distance', forward: height } })],
  });
  return (await d.kernel('doc.get')).document.features.at(-1).id;
}

/** Largest deviation per kind of button face (rounding, top, wall), in mm. */
async function deviationByFace(d, plate) {
  const { status } = await d.kernel('doc.get');
  const map = await d.kernel('inspection.deviation', { bodies: [], maxDistance: 0.5 });
  const largest = {};
  for (const face of map.faces) {
    const tag = status.bodies.find((body) => body.id === face.body)?.faceTags[face.face] ?? '';
    if (tag.startsWith(`${plate}:`)) continue;
    const kind = tag.includes(':fillet:')
      ? 'rounding'
      : tag.endsWith(':cap:end')
        ? 'top'
        : tag.includes(':side:')
          ? 'wall'
          : null;
    if (kind) largest[kind] = Math.max(largest[kind] ?? 0, face.maxAbs);
  }
  return largest;
}

/** Space until the view shows `visibility` (scan and bodies, the scan, the bodies). */
async function show(d, visibility) {
  for (let presses = 0; (await d.state()).visibility !== visibility; presses += 1) {
    if (presses === 3) throw new Error(`the view does not show ${visibility}`);
    await d.command('view.cycleVisibility');
  }
}

/** Zoom onto the part inside a box: select its triangles, fit the view, select nothing. */
async function zoomTo(d, min, max) {
  const { faces } = await d.kernel('automation.facesInBox', {
    min,
    max,
    facing: null,
    maxAngleDeg: 30,
  });
  await d.ui({ type: 'selectFaces', faces });
  await d.command('view.fitSelection');
  await d.command('selection.clear');
}

/** Close-ups of a round and the inclined button: bodies only (colours off), with the
 * scan, with the finished heatmap. */
async function look(d, name) {
  const top = 10 + ROUNDED.round.height;
  const [rx, ry] = ROUNDED.round.centres[0];
  const [ix, iy] = ROUNDED.inclined.centre;
  const views = {
    round: [
      [rx - 6, ry - 6, 9],
      [rx + 6, ry + 6, top + 1],
    ],
    inclined: [
      [ix - 7, iy - 7, 9],
      [ix + 7, iy + 7, top + 1],
    ],
  };
  await d.command('view.iso');
  for (const [button, [min, max]] of Object.entries(views)) {
    await show(d, 'both');
    await zoomTo(d, min, max);
    await show(d, 'bodies');
    await d.shot(`${name}-${button}-bodies`);
    await show(d, 'both');
    await d.shot(`${name}-${button}-scan`);
  }
  await d.press('stage-inspect');
  await d.press('tool-deviation');
  const revision = (await d.state()).revision;
  await d.until(async () => {
    const { deviation } = await d.state();
    return deviation.shown && deviation.revision === revision;
  }, 'the finished deviation map');
  for (const [button, [min, max]] of Object.entries(views)) {
    await zoomTo(d, min, max);
    await d.shot(`${name}-${button}-heatmap`);
  }
  await d.key('Escape');
  await d.press('stage-model');
}

export async function roundingTest(d) {
  const plate = await plateBody(d);
  await d.press('stage-model');
  await d.command('view.iso');
  await d.command('view.fitAll');
  const { round, inclined } = await recognise(d);
  d.check(
    'both round buttons share the rounding from the scan',
    near(round?.rounding, ROUNDED.round.rounding, 1e-6),
    `R ${round?.rounding}`,
  );
  d.check(
    'the inclined top is found with its tilt and no rounding',
    near(inclined?.tilt * DEGREES, ROUNDED.inclined.tiltDeg, 1) && inclined?.rounding === 0,
    `${(inclined?.tilt * DEGREES).toFixed(1)}°, R ${inclined?.rounding}`,
  );
  await d.press(`recognize-round-${round.id}`);
  const off = (await d.toolInfo()).groups.find((group) => group.id === round.id);
  await d.press(`recognize-round-${round.id}`);
  const on = (await d.toolInfo()).groups.find((group) => group.id === round.id);
  d.check('a click on R switches the rounding off and on', !off.rounded && on.rounded);
  await d.shot('rounding-1-found');

  const first = await build(d);
  const state = (feature) => first.snapshot.status.features[feature.id]?.state;
  d.check(
    'every built feature is fine',
    first.added.every((feature) => state(feature) === 'ok' || state(feature) === 'warning'),
    first.added.map((feature) => `${feature.type} ${state(feature)}`).join(', '),
  );
  const fillets = first.added.filter((feature) => feature.type === 'fillet');
  d.check(
    'one fillet R 0,5 for the group of round buttons',
    fillets.length === 1 &&
      fillets[0].params.size === 0.5 &&
      fillets[0].params.targetBody === plate,
    fillets.map((feature) => feature.params.size).join(', '),
  );
  const toPlane = first.added.filter(
    (feature) => feature.type === 'extrude' && feature.params.extent.type === 'toPlane',
  );
  d.check('the inclined button is extruded up to a fitted plane', toPlane.length === 1);
  const largest = await deviationByFace(d, plate);
  d.check(
    'roundings, tops and walls stay within the tolerance',
    Object.values(largest).every((value) => value <= TOLERANCE_MM),
    Object.entries(largest)
      .map(([kind, value]) => `${kind} ${value.toFixed(3)}`)
      .join(', '),
  );
  await look(d, 'rounding-2-built');

  // Built again without the rounding: the fillet tool measures the same radius.
  await d.command('edit.undo');
  await recognise(d);
  await d.press(`recognize-round-${round.id}`);
  const second = await build(d);
  d.check(
    'without the rounding no fillet is built',
    second.added.every((feature) => feature.type !== 'fillet'),
  );
  // Body edges can be picked where they are drawn.
  await d.command('view.display.shadedEdges');
  await d.press('tool-fillet');
  const [x, y] = ROUNDED.round.centres[0];
  const top = 10 + ROUNDED.round.height;
  await d.tap(await d.at([x, y - ROUNDED.round.radius, top]));
  await d.until(async () => (await d.toolInfo())?.edges === 1, 'the picked edge');
  await d.press('fillet-from-scan');
  const measured = await d.until(async () => {
    const info = await d.toolInfo();
    return info?.measurement && info.measurement.status !== 'running' ? info : null;
  }, 'the radius from the scan');
  d.check(
    'Radius aus Scan finds R 0,5 on the picked edge',
    measured.measurement.status === 'ok' && near(measured.size, ROUNDED.round.rounding, 1e-6),
    JSON.stringify(measured.measurement),
  );
  await d.shot('rounding-3-fillet-tool');
  await d.key('Escape');
  await d.command('view.display.shaded');
}
