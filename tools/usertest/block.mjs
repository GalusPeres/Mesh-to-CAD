// A synthetic part for a rounding the extrusion does not have: a block whose long top
// edge at the back is rounded. A sketch and an extrusion give the sharp block; a net
// laid on the rounding, pushed past the block's faces and trimmed with it, rounds the
// edge (issue #7). Written as a binary STL with about 1 mm triangles.

import { writeBinaryStl } from './stl.mjs';

/** Where things are on the block, in millimetres. */
export const BLOCK = {
  size: [60, 40, 20],
  /** Radius of the rounded edge along x at the back (y = 40) of the top (z = 20). */
  radius: 6,
};

/** The block's volume: the sharp block less the corner the rounding removes. */
export function blockVolume() {
  const [x, y, z] = BLOCK.size;
  const r = BLOCK.radius;
  return x * y * z - x * (r * r - (Math.PI * r * r) / 4);
}

/** The cross-section (y, z), counter-clockwise seen from +x, in about 1 mm steps. */
function profile() {
  const [, y, z] = BLOCK.size;
  const r = BLOCK.radius;
  const line = (a, b) => {
    const steps = Math.max(1, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1])));
    return Array.from({ length: steps }, (_, i) => [
      a[0] + ((b[0] - a[0]) * i) / steps,
      a[1] + ((b[1] - a[1]) * i) / steps,
    ]);
  };
  const steps = 24;
  const arc = Array.from({ length: steps }, (_, i) => {
    const angle = (Math.PI / 2) * (i / steps);
    return [y - r + r * Math.cos(angle), z - r + r * Math.sin(angle)];
  });
  return [
    ...line([0, 0], [y, 0]),
    ...line([y, 0], [y, z - r]),
    ...arc,
    ...line([y - r, z], [0, z]),
    ...line([0, z], [0, 0]),
  ];
}

/** Write the block to `file`; returns the number of triangles. */
export function writeBlockPart(file) {
  const [length, depth, height] = BLOCK.size;
  const loop = profile();
  const rows = length;
  const at = (x, [y, z]) => [x, y, z];
  const triangles = [];
  loop.forEach((a, i) => {
    const b = loop[(i + 1) % loop.length];
    for (let k = 0; k < rows; k += 1) {
      const x0 = (length * k) / rows;
      const x1 = (length * (k + 1)) / rows;
      triangles.push([at(x0, a), at(x0, b), at(x1, b)], [at(x0, a), at(x1, b), at(x1, a)]);
    }
  });
  // End caps: fans from the middle of the convex section.
  const centre = [depth / 2, height / 2];
  loop.forEach((a, i) => {
    const b = loop[(i + 1) % loop.length];
    triangles.push([at(length, centre), at(length, a), at(length, b)]);
    triangles.push([at(0, centre), at(0, b), at(0, a)]);
  });
  return writeBinaryStl(file, triangles, 'Mesh-to-CAD user test block');
}
