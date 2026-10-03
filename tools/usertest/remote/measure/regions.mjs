// Sort the scan's points into the regions the user looks at: the underside, the walls,
// the four vertical corners, the top edge, the top face and each button or pocket on
// the top. The regions come from the scan and the two fitted planes only, so they are
// the same in every run, whatever was built.
//
// Front is the end at -Y (the view "Vorne"), left is -X. Heights are measured from the
// fitted top and bottom planes.

import { planeHeight } from '../scene.mjs';
import { components, createGrid, grow, outlineDistance } from './grid.mjs';

const CELL = 0.4;
/** A point this close to the top plane (mm), facing up, lies on the top face. */
const ON_TOP = 0.15;
/** The top edge: points less than this below the top plane, near the outline. */
const EDGE_DEPTH = 1.5;
const EDGE_BAND = 3;
/** Shapes on the top start this far inside the outline (the edge rounding is outside). */
const SHAPE_INSET = 2;
/** Cells around a shape that still belong to it (its flanks down to the top face). */
const FLANK_CELLS = 2;
/** Side of the square at each corner of the outline that counts as the vertical corner. */
const CORNER = 8;
const UNDERSIDE_BAND = 0.3;
/** Without a recognition, fewer points than this off the top face are noise. */
const MIN_SHAPE_POINTS = 1000;

const CORNERS = [
  ['corner front-left', 0, 0],
  ['corner front-right', 1, 0],
  ['corner back-left', 0, 1],
  ['corner back-right', 1, 1],
];

/** The recognised shapes whose label lies in a group's cells. */
function shapesIn(group, shapes, cellOf, label) {
  const inside = shapes.filter((shape) => label[cellOf(shape.at[0], shape.at[1])] === group);
  return [...new Set(inside.map((shape) => shape.shape))].sort();
}

/**
 * The region of every point: `region[i]` indexes `names`. `points` and `normals` are
 * flat (k, 3) arrays in part coordinates, `planes` the fitted top and bottom planes,
 * `shapes` the recognised shapes ({ shape, at }) for naming.
 */
export function classify(points, normals, planes, shapes = []) {
  const count = points.length / 3;
  const min = [Infinity, Infinity];
  const max = [-Infinity, -Infinity];
  for (let i = 0; i < count; i += 1) {
    for (let axis = 0; axis < 2; axis += 1) {
      min[axis] = Math.min(min[axis], points[i * 3 + axis]);
      max[axis] = Math.max(max[axis], points[i * 3 + axis]);
    }
  }
  const grid = createGrid(min, max, CELL);
  const cellOf = grid.index;
  const height = new Float32Array(count);
  const occupied = new Uint8Array(grid.size);
  const upward = new Uint32Array(grid.size);
  const onTop = new Uint32Array(grid.size);
  for (let i = 0; i < count; i += 1) {
    const [x, y, z] = [points[i * 3], points[i * 3 + 1], points[i * 3 + 2]];
    const cell = cellOf(x, y);
    occupied[cell] = 1;
    height[i] = z - planeHeight(planes.top, x, y);
    if (normals[i * 3 + 2] > 0.3 && height[i] > -3) {
      upward[cell] += 1;
      if (Math.abs(height[i]) < ON_TOP && normals[i * 3 + 2] > 0.95) onTop[cell] += 1;
    }
  }
  const distance = outlineDistance(grid, occupied);

  // Shapes: groups of top cells that are not flat at the top plane's height. Flat
  // islands enclosed by a shape (a button's flat cap) belong to that shape.
  const off = new Uint8Array(grid.size);
  const flat = new Uint8Array(grid.size);
  for (let cell = 0; cell < grid.size; cell += 1) {
    if (!upward[cell] || distance[cell] < SHAPE_INSET) continue;
    if (onTop[cell] * 2 > upward[cell]) flat[cell] = 1;
    else off[cell] = 1;
  }
  const { label: raw } = components(grid, off);
  const plains = components(grid, flat);
  const largest = plains.sizes.indexOf(Math.max(...plains.sizes));
  const island = (cell) => flat[cell] === 1 && plains.label[cell] !== largest;
  const label = grow(grid, grow(grid, raw, FLANK_CELLS), 1_000, island);

  const names = ['underside', 'walls', ...CORNERS.map(([name]) => name), 'top edge', 'top face'];
  const fixed = Object.fromEntries(names.map((name, index) => [name, index]));
  const region = new Uint16Array(count);
  const groupOf = new Int32Array(count).fill(-1);
  const sums = new Map();
  for (let i = 0; i < count; i += 1) {
    const [x, y, z] = [points[i * 3], points[i * 3 + 1], points[i * 3 + 2]];
    const nz = normals[i * 3 + 2];
    const cell = cellOf(x, y);
    const h = height[i];
    if (nz < -0.5 || z - planeHeight(planes.bottom, x, y) < UNDERSIDE_BAND) {
      region[i] = fixed.underside;
    } else if (h > -3 && label[cell] >= 0) {
      groupOf[i] = label[cell];
      const sum = sums.get(label[cell]) ?? [0, 0, 0];
      sums.set(label[cell], [sum[0] + x, sum[1] + y, sum[2] + 1]);
      region[i] = fixed['top face'];
    } else if (h > -3 && distance[cell] > EDGE_BAND) {
      region[i] = fixed['top face'];
    } else if (h > -EDGE_DEPTH) {
      region[i] = nz >= 0.97 && Math.abs(h) < ON_TOP ? fixed['top face'] : fixed['top edge'];
    } else {
      const corner = CORNERS.findIndex(
        ([, cx, cy]) =>
          Math.abs(x - (cx ? max[0] : min[0])) < CORNER &&
          Math.abs(y - (cy ? max[1] : min[1])) < CORNER,
      );
      region[i] = corner >= 0 ? fixed[CORNERS[corner][0]] : fixed.walls;
    }
  }

  // Shapes in order along the part, named by what was recognised in them and where
  // they are. Groups without a recognised shape are noise along the top edge; without
  // any recognition only the large groups count.
  const details = names.map((name) => ({ name, shapes: [] }));
  const regionOf = new Map();
  const groups = [...sums.entries()]
    .map(([group, [sx, sy, n]]) => ({
      group,
      centre: [sx / n, sy / n],
      points: n,
      shapes: shapesIn(group, shapes, cellOf, label),
    }))
    .filter((item) => (shapes.length ? item.shapes.length > 0 : item.points >= MIN_SHAPE_POINTS))
    .sort((a, b) => a.centre[1] - b.centre[1] || a.centre[0] - b.centre[0]);
  for (const { group, centre, shapes: kinds } of groups) {
    regionOf.set(group, details.length);
    const where = `x${Math.round(centre[0])} y${Math.round(centre[1])}`;
    details.push({
      name: `${kinds.length ? kinds.join('+') : 'shape'} ${where}`,
      shapes: kinds,
      centre: centre.map((value) => +value.toFixed(2)),
    });
  }
  for (let i = 0; i < count; i += 1) {
    if (regionOf.has(groupOf[i])) region[i] = regionOf.get(groupOf[i]);
  }
  return { region, regions: details, outline: { min, max } };
}
