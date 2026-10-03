// The fitted planes in the view. Tools that end at a plane need it shown; before the
// part is judged, the user clears the view: planes no feature has used are still drawn
// as large plates over the part (used ones are hidden by the app).

import { planeHeight } from './scene.mjs';
import { setView } from './view.mjs';

/**
 * Whether a plane is drawn: a click on its origin, or just beside the part where only
 * the plate reaches, finds the plane (plates are drawn in front of the scan). Seen from
 * above for the top, from below for the bottom.
 */
async function drawn(d, plane, bounds, view) {
  await setView(d, view);
  const { min, max } = bounds;
  const [x, y] = plane.origin;
  const beside = [
    [x, y],
    [min[0] - 1.5, y],
    [max[0] + 1.5, y],
    [x, min[1] - 1.5],
    [x, max[1] + 1.5],
  ];
  for (const [bx, by] of beside) {
    const screen = await d.at([bx, by, planeHeight(plane, bx, by)]).catch(() => null);
    const hit = screen && (await d.pick(screen));
    if (hit?.kind === 'item' && hit.owner === plane.id) return true;
  }
  return false;
}

const VIEWS = { top: 'top', bottom: 'bottom' };

/**
 * Show or hide the fitted planes with the eye in the tree, checking what is drawn first:
 * the eye toggles, and a new project may start with an id hidden already (#38).
 * Returns what could not be done.
 */
export async function showPlanes(ctx, show) {
  const { d, planes, bounds } = ctx;
  if (!planes) return [];
  const problems = [];
  for (const [name, view] of Object.entries(VIEWS)) {
    const plane = planes[name];
    if ((await drawn(d, plane, bounds, view)) === show) continue;
    await d.press(`tree-eye-${plane.id}`);
    if ((await drawn(d, plane, bounds, view)) !== show) {
      problems.push(`the eye does not ${show ? 'show' : 'hide'} the ${name} plane`);
    }
  }
  return problems;
}
