// The rounded block of the loft-to-plane test: a rectangle with rounded corners, its top
// edge rounded too, written as binary STL with triangles of about 1 mm.

import { writeStl } from './part.mjs';

/** The block from the origin, in millimetres. */
export const BLOCK = {
  /** Length (x), width (y), height (z). */
  size: [60, 30, 20],
  /** Radius of the vertical corners. */
  corner: 6,
  /** Radius of the rounding along the top edge (the fillet tool's default). */
  top: 2,
};

const ARC_STEPS = 12;

/** The outline `inset` mm inside the block's at height z, counter-clockwise. */
function ring(inset, z) {
  const [length, width] = BLOCK.size;
  const radius = BLOCK.corner - inset;
  const centres = [
    [length - BLOCK.corner, width - BLOCK.corner],
    [BLOCK.corner, width - BLOCK.corner],
    [BLOCK.corner, BLOCK.corner],
    [length - BLOCK.corner, BLOCK.corner],
  ];
  const points = [];
  centres.forEach((centre, corner) => {
    const next = centres[(corner + 1) % 4];
    for (let i = 0; i < ARC_STEPS; i += 1) {
      const angle = ((corner + i / ARC_STEPS) * Math.PI) / 2;
      points.push([centre[0] + radius * Math.cos(angle), centre[1] + radius * Math.sin(angle), z]);
    }
    // The straight side to the next corner, about 1 mm per segment.
    const angle = ((corner + 1) * Math.PI) / 2;
    const from = [centre[0] + radius * Math.cos(angle), centre[1] + radius * Math.sin(angle)];
    const to = [next[0] + radius * Math.cos(angle), next[1] + radius * Math.sin(angle)];
    const steps = Math.max(1, Math.round(Math.hypot(to[0] - from[0], to[1] - from[1])));
    for (let i = 0; i < steps; i += 1) {
      const t = i / steps;
      points.push([from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t, z]);
    }
  });
  return points;
}

/** Quads between two rings with the same number of points (outward for rising rings). */
function band(triangles, lower, upper) {
  lower.forEach((a, i) => {
    const j = (i + 1) % lower.length;
    triangles.push([a, lower[j], upper[j]], [a, upper[j], upper[i]]);
  });
}

/** A flat cap over a ring: rings shrinking to the centre; `up` gives its normal. */
function cap(triangles, outer, up) {
  const [length, width] = BLOCK.size;
  const centre = [length / 2, width / 2];
  const steps = 15;
  const scaled = (k) =>
    outer.map(([x, y, z]) => [
      centre[0] + ((x - centre[0]) * k) / steps,
      centre[1] + ((y - centre[1]) * k) / steps,
      z,
    ]);
  for (let k = 0; k < steps; k += 1) {
    const [inner, outerRing] = [scaled(k), scaled(k + 1)];
    outerRing.forEach((a, i) => {
      const j = (i + 1) % outerRing.length;
      const quad = [
        [inner[i], a, outerRing[j]],
        [inner[i], outerRing[j], inner[j]],
      ];
      // The innermost ring is the centre: its quads are single triangles.
      for (const triangle of k === 0 ? quad.slice(0, 1) : quad) {
        triangles.push(up ? triangle : [...triangle].reverse());
      }
    });
  }
}

/** Write the block to `file`; returns the number of triangles. */
export function writeRoundedBlock(file) {
  const height = BLOCK.size[2];
  const { top } = BLOCK;
  const rings = [];
  for (let z = 0; z < height - top; z += 1) rings.push(ring(0, z));
  for (let k = 0; k <= ARC_STEPS; k += 1) {
    const angle = (k / ARC_STEPS) * (Math.PI / 2);
    rings.push(ring(top * (1 - Math.cos(angle)), height - top + top * Math.sin(angle)));
  }
  const triangles = [];
  for (let k = 0; k + 1 < rings.length; k += 1) band(triangles, rings[k], rings[k + 1]);
  cap(triangles, rings[0], false);
  cap(triangles, rings[rings.length - 1], true);
  return writeStl(file, triangles);
}

/** The block's true volume: the outline times the height, less the top rounding. */
export function roundedBlockVolume() {
  const [length, width, height] = BLOCK.size;
  const { corner, top } = BLOCK;
  const area = length * width - (4 - Math.PI) * corner * corner;
  // The rounding removes (1 - pi/4) r^2 along a path through the removed area's centroid,
  // which lies (10 - 3 pi) / (12 - 3 pi) r inside the walls (Pappus).
  const inset = (top * (10 - 3 * Math.PI)) / (12 - 3 * Math.PI);
  const path =
    2 * (length - 2 * corner) + 2 * (width - 2 * corner) + 2 * Math.PI * (corner - inset);
  return area * height - (1 - Math.PI / 4) * top * top * path;
}
