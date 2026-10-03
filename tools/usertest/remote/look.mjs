// Look at the result the way the user does (AGENTS.md, "Done means" 3): the heatmap
// computed to the end in Prüfen → Abweichung, then the whole part from five sides and
// close-ups of every vertical corner and of the D-pad, each as bodies only with the
// colours off, with the scan, and as the heatmap.

import { MODES, setView, showMode, turn, zoomTo } from './view.mjs';

const VIEWS = ['iso', 'top', 'bottom', 'front', 'right'];

/** The four vertical corners, with the quarter turns from the iso view (front-right). */
const CORNERS = [
  { name: 'front-right', x: 1, y: 0, degrees: 0 },
  { name: 'front-left', x: 0, y: 0, degrees: -90 },
  { name: 'back-left', x: 0, y: 1, degrees: 180 },
  { name: 'back-right', x: 1, y: 1, degrees: 90 },
];
const CORNER_BOX = 9;

/** Prüfen → Abweichung, waiting until the map is computed for the current revision. */
export async function heatmap(d) {
  await d.key('Escape');
  await d.press('stage-inspect');
  await d.press('tool-deviation');
  const started = Date.now();
  await d.until(
    async () => {
      const state = await d.state();
      return state.deviation.revision !== null && state.deviation.revision === state.revision;
    },
    'the finished heatmap',
    600_000,
  );
  const seconds = +((Date.now() - started) / 1000).toFixed(1);
  await d.shot('heatmap-panel');
  await d.key('Escape');
  return seconds;
}

/** The three pictures of the current camera, named `<name>-<mode>`. */
async function threeWays(d, name, shots) {
  for (const mode of Object.keys(MODES)) {
    await showMode(d, mode);
    await d.shot(`${name}-${mode}`);
    shots.push(`${name}-${mode}.png`);
  }
}

/** Where the D-pad is: the box around the recognised ring segments, or null. */
function dpadBox(shapes, top) {
  const ring = (shapes ?? []).filter((shape) => shape.shape === 'ringSegment');
  if (ring.length === 0) return null;
  const xs = ring.map((shape) => shape.at[0]);
  const ys = ring.map((shape) => shape.at[1]);
  const margin = 5;
  return {
    min: [Math.min(...xs) - margin, Math.min(...ys) - margin, top - 4],
    max: [Math.max(...xs) + margin, Math.max(...ys) + margin, top + 4],
  };
}

/** Every picture; returns their file names and what could not be taken. */
export async function look(ctx) {
  const { d, bounds } = ctx;
  const shots = [];
  const problems = [];
  const { min, max } = bounds;
  const centre = min.map((value, axis) => (value + max[axis]) / 2);

  for (const view of VIEWS) {
    await setView(d, view);
    await threeWays(d, `view-${view}`, shots);
  }
  for (const corner of CORNERS) {
    try {
      const x = corner.x ? max[0] : min[0];
      const y = corner.y ? max[1] : min[1];
      await setView(d, 'iso', 'scan');
      await turn(d, corner.degrees, centre);
      await zoomTo(
        d,
        [x - CORNER_BOX, y - CORNER_BOX, min[2]],
        [x + CORNER_BOX, y + CORNER_BOX, max[2]],
      );
      await threeWays(d, `corner-${corner.name}`, shots);
    } catch (error) {
      problems.push(`corner ${corner.name}: ${error.message}`);
    }
  }
  const top = ctx.planes?.top.origin[2] ?? max[2];
  const box = dpadBox(ctx.shapes, top);
  if (box) {
    await setView(d, 'iso', 'scan');
    await zoomTo(d, box.min, box.max);
    await threeWays(d, 'dpad', shots);
  } else {
    problems.push('D-pad: no ring segments were recognised');
  }
  await setView(d, 'iso', 'scan');
  return { shots, problems };
}
