// Step: the base body as a net, the QuickSurface way (docs/research/quicksurface.md,
// workflow step 7): an auto net on everything below the button face, pushed past the
// top plane, then Zuschneiden with that plane makes one closed solid.

import { bodyOf, shown, snapshot } from '../scene.mjs';

/** The net covers the scan up to this far below the top plane (mm). */
const BELOW_TOP = 0.4;

const featuresOf = async (d, type) =>
  (await snapshot(d)).document.features.filter((feature) => feature.type === type);

/** Zuschneiden's preview once it is computed. */
async function trimPreview(d) {
  await d.pause(500);
  return d.until(
    async () => {
      const info = await d.toolInfo();
      return info?.preview === 'ok' || info?.preview === 'error' ? info : null;
    },
    'the Zuschneiden preview',
    300_000,
  );
}

export const baseNet = {
  id: 'base',
  title: 'Base body: auto net below the top, pushed past the plane, Zuschneiden',
  async run(ctx) {
    const { d } = ctx;
    if (!ctx.planes) throw new Error('the net needs the top plane');
    const { min, max } = ctx.bounds;
    const top = ctx.planes.top;
    const started = Date.now();

    await d.press('stage-model');
    await setIso(d);
    const { faces } = await d.kernel('automation.facesInBox', {
      min: [min[0] - 1, min[1] - 1, min[2] - 1],
      max: [max[0] + 1, max[1] + 1, top.origin[2] - BELOW_TOP],
    });
    await d.select(faces);
    await d.press('tool-freeform-net');
    await d.key('Escape');
    await d.press('freeform-net-source-selection');
    await d.press('freeform-net-density-medium');
    await d.press('freeform-net-generate');
    await d.settle(600_000);
    const net = await d.toolInfo();
    await d.shot('base-1-net');

    await d.press('freeform-net-push');
    await d.settle(300_000);
    const pushed = (await d.toolInfo())?.state?.pushed ?? null;
    await d.shot('base-2-pushed');
    await d.pressWhenReady('panel-ok', 300_000);
    await d.until(async () => (await featuresOf(d, 'freeformNet')).length > 0, 'the net', 300_000);
    await shown(d);

    await d.select([]);
    await d.press('tool-trim-solid');
    await d.press(`trim-solid-planes-${top.id}`);
    const trim = await trimPreview(d);
    if (!trim.canCommit) {
      await d.press('panel-cancel').catch(() => undefined);
      throw new Error(`Zuschneiden: ${trim.error ?? trim.preview}, ${trim.stats?.pieces} pieces`);
    }
    await d.pressWhenReady('panel-ok', 300_000);
    const [feature] = await d.until(
      async () => {
        const trims = await featuresOf(d, 'trimSolid');
        return trims.length && (await bodyOf(d, trims[0].id)) ? trims : null;
      },
      'the trimmed body',
      300_000,
    );
    await shown(d);
    const body = await bodyOf(d, feature.id);
    ctx.body = body.id;
    const preflight = await d.kernel('export.preflight', { bodies: [body.id] });
    const check = preflight.bodies.find((item) => item.body === body.id);
    return {
      seconds: +((Date.now() - started) / 1000).toFixed(1),
      quads: net?.quads ?? null,
      pushed,
      pieces: trim.stats?.pieces ?? null,
      valid: body.valid,
      solids: body.solids,
      volumeMm3: Math.round(body.volume),
      closed: check?.closed ?? null,
      gaps: check && !check.blocking ? [] : [`export check: ${JSON.stringify(check?.problems)}`],
    };
  },
};

async function setIso(d) {
  await d.command('view.iso');
  await d.command('view.fitAll');
}
