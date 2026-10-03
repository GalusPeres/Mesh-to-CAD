// Step: the base body as a loft along Z through the scan's walls (Loft with its
// default range and 12 sections, OK), as the user builds it today. When the loft can
// end at the top and bottom planes (#22), or nets build the walls, only this step changes.

import { bodyOf, shown, snapshot } from '../scene.mjs';

export const baseLoft = {
  id: 'base',
  title: 'Base body: Loft along Z, default range, OK',
  async run(ctx) {
    const { d } = ctx;
    await d.press('stage-model');
    await d.command('view.iso');
    const opened = Date.now();
    await d.press('tool-loft');
    // OK is enabled once the preview is there.
    const loft = await d.until(
      async () => {
        await d.press('panel-ok').catch(() => undefined);
        const { document } = await snapshot(d);
        const feature = document.features.find((item) => item.type === 'loft');
        return feature && (await bodyOf(d, feature.id)) ? feature : null;
      },
      'the loft',
      180_000,
    );
    await shown(d);
    const { status } = await snapshot(d);
    const body = await bodyOf(d, loft.id);
    ctx.body = body.id;
    const stats = status.features[loft.id]?.stats ?? {};
    return {
      seconds: +((Date.now() - opened) / 1000).toFixed(1),
      range: [loft.params.start, loft.params.end],
      sections: stats['freeform.stats.sections'] ?? loft.params.sectionCount,
      sectionMaxMm: stats['freeform.stats.sectionMax'],
      valid: body.valid,
      faces: body.faceTags.length,
      volumeMm3: Math.round(body.volume),
    };
  },
};
