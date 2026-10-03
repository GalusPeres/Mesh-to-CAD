// User test of Formen erkennen (#11): on a plate with a button cut by the plate's end,
// a whole button and a keyhole-shaped button, the recognition names the cut circle,
// keeps the keyhole as a free outline of lines and arcs, checks all of them, and OK
// builds every one as sketch and extrusion that stays on the scan.

import { BUTTONS, PART } from './part.mjs';

const near = (value, expected, tolerance) =>
  typeof value === 'number' && Math.abs(value - expected) <= tolerance;

/** The groups the open panel lists, once the recognition has finished. */
async function recognised(d) {
  return d.until(async () => {
    const info = await d.toolInfo();
    return !info?.state?.job && info?.groups?.length ? info.groups : null;
  }, 'the recognised shapes');
}

export async function recognizeTest(d) {
  await d.press('stage-model');
  await d.press('tool-recognize');
  await d.command('view.top');
  await d.command('view.fitAll');
  const groups = await recognised(d);
  const shape = (name) => groups.find((group) => group.shape === name);

  const cut = shape('cutCircle');
  const reach = PART.plate[0] - BUTTONS.cut.centre[0];
  d.check(
    'the button cut by the end is a cut circle',
    near(cut?.params.radius, BUTTONS.cut.radius, 0.05) && near(cut?.params.cut, reach, 0.1),
    JSON.stringify(cut?.params),
  );
  const whole = shape('circle');
  d.check('the whole button is a circle', near(whole?.params.radius, BUTTONS.whole.radius, 0.05));
  const free = shape('profile');
  const { radius, tail, centre } = BUTTONS.keyhole;
  d.check(
    'the keyhole is a free outline',
    near(free?.params.width, tail - centre[0] + radius, 0.1) &&
      near(free?.params.height, 2 * radius, 0.1),
    JSON.stringify(free?.params),
  );
  d.check(
    'every shape is checked to be built',
    groups.every((group) => group.checked),
  );
  await d.shot('recognize-1-found');

  const before = (await d.kernel('doc.get')).document.features.length;
  await d.press('panel-ok');
  const snapshot = await d.until(async () => {
    const current = await d.kernel('doc.get');
    return current.document.features.length > before ? current : null;
  }, 'the built shapes');
  const added = snapshot.document.features.slice(before);
  const status = (feature) => snapshot.status.features[feature.id] ?? {};
  d.check(
    'every built feature is fine',
    added.every((feature) => status(feature).state === 'ok'),
    added.map((feature) => `${feature.type} ${status(feature).state}`).join(', '),
  );
  const sketch = added.find((feature) => feature.type === 'sketch');
  const stats = sketch ? (status(sketch).stats ?? {}) : {};
  d.check(
    'one sketch of lines and arcs: an arc and a line, a circle, an arc and three lines',
    stats['sketch.loops'] === 3 && stats['sketch.entities'] === 7,
    JSON.stringify(stats),
  );
  // Within the project tolerance (0.05 mm); a perfect fit reads about 0.025 mm, the
  // spacing of the section points it is measured against.
  d.check(
    'the sketch stays on the scan',
    near(stats['sketch.deviation'], 0, 0.05),
    `${stats['sketch.deviation']} mm`,
  );
  const extrusions = added.filter((feature) => feature.type === 'extrude');
  d.check('every button becomes a body', extrusions.length === 3, `${extrusions.length}`);
  await d.command('view.iso');
  await d.command('view.fitAll');
  await d.shot('recognize-2-built');
}
