// Step: planes fitted to the top face and the underside (Form einpassen on a
// selection), robust so the buttons on the top and the lid recess below are left out.

import { applyOps, snapshot, uint32 } from '../scene.mjs';
import { setView } from '../view.mjs';

/** Fit a plane to the scan triangles in a box facing a direction and add it. */
async function fitPlane(d, min, max, facing) {
  const { faces } = await d.kernel('automation.facesInBox', {
    min,
    max,
    facing,
    maxAngleDeg: 10,
  });
  if (faces.length === 0) throw new Error(`no triangles facing ${facing} in the box`);
  const { document } = await snapshot(d);
  const preview = await d.kernel(
    'fit.preview',
    { faces: uint32(faces), scanKey: document.scan.key, kind: 'plane', robust: true },
    'fit.preview:remote',
  );
  await applyOps(
    d,
    [
      {
        type: 'addFeature',
        feature: { type: 'fit', params: { faces: uint32(faces), kind: 'plane', robust: true } },
      },
    ],
    'fit',
  );
  const { document: after } = await snapshot(d);
  const { origin, normal } = preview.primitive;
  return { id: after.features.at(-1).id, origin, normal, rms: preview.stats.rms };
}

/**
 * Whether a plane is drawn: a click just beside the part, where only the plane's plate
 * reaches, finds the plane. Seen from above for the top, from below for the bottom.
 */
async function drawn(d, plane, bounds, view) {
  await setView(d, view);
  const beside = [bounds.min[0] - 1.5, (bounds.min[1] + bounds.max[1]) / 2, plane.origin[2]];
  const hit = await d.pick(await d.at(beside));
  return hit?.kind === 'item' && hit.owner === plane.id;
}

/** Hide a plane with the eye in the tree, the way the user clears the view. */
async function hide(d, plane, bounds, view) {
  // The eye toggles, and a new project may start with an id hidden already (#38).
  if (!(await drawn(d, plane, bounds, view))) return null;
  await d.press(`tree-eye-${plane.id}`);
  return (await drawn(d, plane, bounds, view)) ? `the eye does not hide plane ${plane.id}` : null;
}

export const planes = {
  id: 'planes',
  title: 'Top and bottom planes (Form einpassen, robust)',
  async run(ctx) {
    const { min, max } = ctx.bounds;
    const height = max[2] - min[2];
    const top = await fitPlane(
      ctx.d,
      [min[0], min[1], min[2] + 0.75 * height],
      [max[0], max[1], max[2]],
      [0, 0, 1],
    );
    const bottom = await fitPlane(
      ctx.d,
      [min[0], min[1], min[2] - 1],
      [max[0], max[1], min[2] + 0.06 * height],
      [0, 0, -1],
    );
    ctx.planes = { top, bottom };
    // No feature uses them yet, so they stay drawn as large plates over the part; the
    // user hides them with the eye in the tree.
    const gaps = [
      await hide(ctx.d, top, ctx.bounds, 'top'),
      await hide(ctx.d, bottom, ctx.bounds, 'bottom'),
    ].filter(Boolean);
    const describe = (plane) => ({
      z: +plane.origin[2].toFixed(3),
      tiltDeg: +((Math.acos(Math.abs(plane.normal[2])) * 180) / Math.PI).toFixed(2),
      rms: +plane.rms.toFixed(4),
    });
    return { top: describe(top), bottom: describe(bottom), gaps };
  },
};
