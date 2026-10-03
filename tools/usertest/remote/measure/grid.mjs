// A square grid over the part's footprint (seen from above): which cells hold scan,
// how far each cell is from the outline, and connected groups of marked cells.

const NEIGHBOURS = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];

export function createGrid(min, max, cell) {
  const columns = Math.ceil((max[0] - min[0]) / cell) + 3;
  const rows = Math.ceil((max[1] - min[1]) / cell) + 3;
  const index = (x, y) => {
    const column = Math.floor((x - min[0]) / cell) + 1;
    const row = Math.floor((y - min[1]) / cell) + 1;
    return row * columns + column;
  };
  return { columns, rows, cell, size: columns * rows, index };
}

/** Breadth-first walk from `starts` over cells `open` allows; returns steps per cell. */
function walk(grid, starts, open) {
  const steps = new Int32Array(grid.size).fill(-1);
  const queue = new Int32Array(grid.size);
  let head = 0;
  let tail = 0;
  for (const start of starts) {
    steps[start] = 0;
    queue[tail++] = start;
  }
  while (head < tail) {
    const at = queue[head++];
    const column = at % grid.columns;
    const row = (at - column) / grid.columns;
    for (const [dx, dy] of NEIGHBOURS) {
      const c = column + dx;
      const r = row + dy;
      if (c < 0 || r < 0 || c >= grid.columns || r >= grid.rows) continue;
      const next = r * grid.columns + c;
      if (steps[next] >= 0 || !open(next)) continue;
      steps[next] = steps[at] + 1;
      queue[tail++] = next;
    }
  }
  return steps;
}

/**
 * Distance in mm from each cell to the outside of the footprint. The outside is what
 * a walk from the grid's border reaches without crossing scan, so holes in the scan's
 * top (between buttons) count as inside.
 */
export function outlineDistance(grid, occupied) {
  const border = [];
  for (let c = 0; c < grid.columns; c += 1) border.push(c, (grid.rows - 1) * grid.columns + c);
  for (let r = 0; r < grid.rows; r += 1) border.push(r * grid.columns, r * grid.columns + grid.columns - 1);
  const outside = walk(grid, border, (cell) => !occupied[cell]);
  const edge = [];
  for (let cell = 0; cell < grid.size; cell += 1) if (outside[cell] >= 0) edge.push(cell);
  const steps = walk(grid, edge, () => true);
  return Float32Array.from(steps, (value) => value * grid.cell);
}

/** Connected groups of marked cells: a group number per cell (-1 unmarked), the sizes. */
export function components(grid, marked) {
  const label = new Int32Array(grid.size).fill(-1);
  const sizes = [];
  const queue = new Int32Array(grid.size);
  for (let seed = 0; seed < grid.size; seed += 1) {
    if (!marked[seed] || label[seed] >= 0) continue;
    const group = sizes.length;
    let head = 0;
    let tail = 0;
    label[seed] = group;
    queue[tail++] = seed;
    while (head < tail) {
      const at = queue[head++];
      const column = at % grid.columns;
      const row = (at - column) / grid.columns;
      for (const [dx, dy] of NEIGHBOURS) {
        const c = column + dx;
        const r = row + dy;
        if (c < 0 || r < 0 || c >= grid.columns || r >= grid.rows) continue;
        const cell = r * grid.columns + c;
        if (!marked[cell] || label[cell] >= 0) continue;
        label[cell] = group;
        queue[tail++] = cell;
      }
    }
    sizes.push(tail);
  }
  return { label, sizes };
}

/**
 * Grow labelled groups by `cells` steps into the cells `allowed` accepts (all by
 * default); where two groups meet, the nearer one wins.
 */
export function grow(grid, label, cells, allowed = () => true) {
  const grown = Int32Array.from(label);
  let front = [];
  for (let cell = 0; cell < grid.size; cell += 1) if (label[cell] >= 0) front.push(cell);
  for (let step = 0; step < cells; step += 1) {
    const next = [];
    for (const at of front) {
      const column = at % grid.columns;
      const row = (at - column) / grid.columns;
      for (const [dx, dy] of NEIGHBOURS) {
        const c = column + dx;
        const r = row + dy;
        if (c < 0 || r < 0 || c >= grid.columns || r >= grid.rows) continue;
        const cell = r * grid.columns + c;
        if (grown[cell] >= 0 || !allowed(cell)) continue;
        grown[cell] = grown[at];
        next.push(cell);
      }
    }
    front = next;
  }
  return grown;
}
