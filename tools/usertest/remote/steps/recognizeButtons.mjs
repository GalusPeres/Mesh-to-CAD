// Step: the buttons and pockets on the top, the QuickSurface way of Auto Shapes:
// Formen erkennen, Alle, OK onto the base body (the panel's default target).

import { addedFeatures, shown, snapshot } from '../scene.mjs';

/** The groups the open panel lists, once the recognition has finished. */
function recognised(d) {
  return d.until(
    async () => {
      const info = await d.toolInfo();
      return !info?.state?.job && info?.groups?.length ? info.groups : null;
    },
    'the recognised shapes',
    300_000,
  );
}

export const recognizeButtons = {
  id: 'recognize',
  title: 'Formen erkennen, Alle, OK on the body',
  async run(ctx) {
    const { d } = ctx;
    await d.key('Escape');
    await d.press('stage-model');
    await d.press('tool-recognize');
    const groups = await recognised(d);
    await d.press('recognize-all');
    const before = (await snapshot(d)).document.features.length;
    await d.press('panel-ok');
    await d.until(
      async () => (await d.state()).activeTool !== 'recognize',
      'the built shapes',
      300_000,
    );
    await shown(d);

    // Where the shapes are, for naming the button regions and the D-pad close-up; the
    // panel ran the same recognition, so the kernel answers from its cache.
    const { document } = await snapshot(d);
    const found = await d.kernel(
      'recognize.run',
      { scanKey: document.scan.key },
      'recognize.run:remote',
    );
    ctx.shapes = found.features.map((feature) => ({
      shape: feature.shape,
      role: feature.kind === 'boss' ? 'raised' : feature.top === 'through' ? 'hole' : 'pocket',
      at: feature.label,
      height: feature.height,
    }));

    const added = await addedFeatures(d, before);
    const failed = added.filter((feature) => feature.state === 'error');
    const errors = {};
    for (const feature of failed) errors[feature.error] = (errors[feature.error] ?? 0) + 1;
    return {
      groups: groups.length,
      shapes: groups.reduce((sum, group) => sum + group.count, 0),
      features: added.length,
      failed: failed.length,
      errors,
      gaps: failed.length
        ? [`${failed.length} of ${added.length} features fail: ${JSON.stringify(errors)}`]
        : [],
    };
  },
};
