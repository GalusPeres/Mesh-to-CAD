// A synthetic part with curved walls between two planes, like a remote's sides: an
// elliptic tub whose walls narrow towards the top and bulge out a little, with a flat
// bottom (z = 0) and a flat top. A loft could not follow the bulge exactly; a freeform
// net between the two planes can. Written as a binary STL with about 1 mm triangles.

import { writeBinaryStl } from './stl.mjs';

/** Where things are on the tub, in millimetres. */
export const TUB = {
  centre: [40, 25],
  height: 16,
  /** Semi-axes (x, y) at the bottom and the top; the bulge adds to both at mid-height. */
  bottom: [30, 18],
  top: [25, 15],
  bulge: 1.5,
};

/** Semi-axes of the wall at height z. */
export function semiAxes(z) {
  const t = z / TUB.height;
  const swell = TUB.bulge * Math.sin(Math.PI * t);
  return [0, 1].map((k) => TUB.bottom[k] + (TUB.top[k] - TUB.bottom[k]) * t + swell);
}

/** The tub's volume: the integral of the ellipse areas over the height. */
export function tubVolume(steps = 2000) {
  let volume = 0;
  for (let i = 0; i < steps; i += 1) {
    const [a, b] = semiAxes(((i + 0.5) * TUB.height) / steps);
    volume += (Math.PI * a * b * TUB.height) / steps;
  }
  return volume;
}

/** Write the tub to `file`; returns the number of triangles. */
export function writeTubPart(file, segments = 180, rows = 16, rings = 20) {
  const [cx, cy] = TUB.centre;
  const wall = (i, z) => {
    const angle = (2 * Math.PI * (i % segments)) / segments;
    const [a, b] = semiAxes(z);
    return [cx + a * Math.cos(angle), cy + b * Math.sin(angle), z];
  };
  const cap = (k, i, z) => {
    const [x, y] = wall(i, z);
    return [cx + ((x - cx) * k) / rings, cy + ((y - cy) * k) / rings, z];
  };
  const triangles = [];
  for (let i = 0; i < segments; i += 1) {
    for (let j = 0; j < rows; j += 1) {
      const [z0, z1] = [(TUB.height * j) / rows, (TUB.height * (j + 1)) / rows];
      const [a, b, c, d] = [wall(i, z0), wall(i + 1, z0), wall(i + 1, z1), wall(i, z1)];
      triangles.push([a, b, c], [a, c, d]);
    }
    for (let k = 0; k < rings; k += 1) {
      // Top seen from above and bottom seen from below, both counter-clockwise.
      const top = TUB.height;
      const [a, b, c, d] = [
        cap(k, i, top),
        cap(k + 1, i, top),
        cap(k + 1, i + 1, top),
        cap(k, i + 1, top),
      ];
      triangles.push([a, b, c]);
      if (k > 0) triangles.push([a, c, d]);
      const [e, f, g, h] = [cap(k, i, 0), cap(k, i + 1, 0), cap(k + 1, i + 1, 0), cap(k + 1, i, 0)];
      triangles.push([e, g, h]);
      if (k > 0) triangles.push([e, f, g]);
    }
  }
  return writeBinaryStl(file, triangles, 'Mesh-to-CAD user test tub');
}
