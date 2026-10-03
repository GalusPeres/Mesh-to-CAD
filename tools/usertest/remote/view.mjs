// The view as the user sets it: standard views (number keys), Space for what is shown
// (scan and bodies, scan, bodies), D for the deviation colours, a right drag to turn
// the part, Shift+F to zoom onto a selection.

/** How a picture shows the part: the bodies alone, bodies with the scan, the heatmap. */
export const MODES = {
  bodies: { visibility: 'bodies', deviation: false },
  scan: { visibility: 'both', deviation: false },
  heatmap: { visibility: 'scan', deviation: true },
};

/** Radians the view turns per pixel of a right drag (viewport/CameraRig.ts). */
const ORBIT_RAD_PER_PX = 0.008;

/** Show `mode` (a key of MODES) with the keys a user presses. */
export async function showMode(d, mode) {
  const want = MODES[mode];
  for (let press = 0; press < 3; press += 1) {
    if ((await d.state()).visibility === want.visibility) break;
    await d.command('view.cycleVisibility');
  }
  const state = await d.state();
  if (state.visibility !== want.visibility) throw new Error(`cannot show ${want.visibility}`);
  if (state.deviation.shown !== want.deviation) await d.command('view.deviation');
}

/** A standard view of the whole part, shown as `mode`. */
export async function setView(d, view, mode) {
  await d.command(`view.${view}`);
  await d.command('view.fitAll');
  if (mode) await showMode(d, mode);
}

/**
 * Turn the view around the vertical axis by `degrees` with a right drag across the
 * middle of the part (positive turns the camera counter-clockwise seen from above).
 */
export async function turn(d, degrees, centre) {
  if (!degrees) return;
  const from = await d.at(centre);
  const dx = -((degrees * Math.PI) / 180) / ORBIT_RAD_PER_PX;
  await d.drag(from, { x: from.x + dx, y: from.y }, { button: 2 }, 24);
}

/** Zoom onto the scan triangles in a box, like selecting them and pressing Shift+F. */
export async function zoomTo(d, min, max) {
  const { faces } = await d.kernel('automation.facesInBox', { min, max });
  if (faces.length === 0) throw new Error('nothing of the scan in the close-up box');
  await d.select(faces);
  await d.command('view.fitSelection');
  await d.select([]);
}
