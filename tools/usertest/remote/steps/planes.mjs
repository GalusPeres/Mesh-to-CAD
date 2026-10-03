// Step: planes fitted to the top face and the underside (Form einpassen on a
// selection), robust so the buttons on the top and the lid recess below are left out.

import { applyOps, snapshot, uint32 } from '../scene.mjs';
import { showPlanes } from '../tidy.mjs';

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
    // Pushing a net past a plane needs the plane shown.
    const gaps = await showPlanes(ctx, true);
    const describe = (plane) => ({
      z: +plane.origin[2].toFixed(3),
      tiltDeg: +((Math.acos(Math.abs(plane.normal[2])) * 180) / Math.PI).toFixed(2),
      rms: +plane.rms.toFixed(4),
    });
    return { top: describe(top), bottom: describe(bottom), gaps };
  },
};
