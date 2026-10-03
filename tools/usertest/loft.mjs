// User test of the loft (#16): along Z through the plate with the boss, the default
// range keeps to the plate's walls (not into the boss), the preview comes quickly and OK
// builds a valid solid of the plate's size.

import { PART } from './part.mjs';

const [LENGTH, WIDTH, HEIGHT] = PART.plate;

/** The loft feature and its body once the document has them. */
async function builtLoft(d) {
  const doc = await d.kernel('doc.get');
  const loft = doc.document.features.find((feature) => feature.type === 'loft');
  const body = loft && doc.status.bodies.find((item) => item.owner === loft.id);
  return body ? { status: doc.status.features[loft.id], body } : null;
}

export async function loftTest(d) {
  await d.press('stage-model');
  await d.command('view.iso');
  await d.command('view.fitAll');
  const axis = await d.kernel('freeform.loftAxis', { path: 'Z' });
  const range = `${axis.start.toFixed(2)} … ${axis.end.toFixed(2)} mm`;
  d.check(
    'the range keeps to the plate, below the boss',
    axis.start > 0 && axis.end < HEIGHT,
    range,
  );

  const opened = Date.now();
  await d.press('tool-loft');
  // OK is enabled once the preview is there.
  await d.until(
    async () => {
      await d.press('panel-ok').catch(() => undefined);
      return builtLoft(d);
    },
    'the loft',
    60_000,
  );
  const seconds = (Date.now() - opened) / 1000;
  d.check('the loft is built within 20 s', seconds < 20, `${seconds.toFixed(1)} s`);
  const { status, body } = await builtLoft(d);
  d.check('the loft is a valid solid', body.valid && status.state !== 'error', status.state);
  // The plate's vertical edges are sharp, which a smooth loft rounds past by a few %.
  const plate = LENGTH * WIDTH * (axis.end - axis.start);
  const off = Math.abs(body.volume - plate) / plate;
  d.check('its volume is the plate between the ends', off < 0.1, `${(off * 100).toFixed(1)} % off`);
  await d.shot('loft-1-built');
}
