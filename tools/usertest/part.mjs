// The synthetic part the user tests run on: a plate with a round boss, written as a
// binary STL with about 1 mm triangles, so every position is known in advance.

import { writeFileSync } from 'node:fs';

/** Where things are on the part, in millimetres (the part is not aligned or moved). */
export const PART = {
  /** The plate from the origin: length (x), width (y), height (z). */
  plate: [80, 50, 10],
  /** The boss on the plate's top: centre (x, y), radius, top height. */
  boss: { centre: [20, 25], radius: 10, top: 20 },
};

/** A grid of `nu` x `nv` quads over the parallelogram origin + s*u + t*v (outward u x v). */
function grid(triangles, origin, u, v, nu, nv) {
  const at = (i, j) => origin.map((o, k) => o + (u[k] * i) / nu + (v[k] * j) / nv);
  for (let i = 0; i < nu; i += 1) {
    for (let j = 0; j < nv; j += 1) {
      const [a, b, c, d] = [at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)];
      triangles.push([a, b, c], [a, c, d]);
    }
  }
}

/** The boss: its side and its top disk (rings around the centre). */
function boss(triangles, segments = 64, rows = 10, rings = 10) {
  const { centre, radius, top } = PART.boss;
  const bottom = PART.plate[2];
  const angle = (i) => (2 * Math.PI * (i % segments)) / segments;
  const side = (i, j) => [
    centre[0] + radius * Math.cos(angle(i)),
    centre[1] + radius * Math.sin(angle(i)),
    bottom + ((top - bottom) * j) / rows,
  ];
  const disk = (k, i) => [
    centre[0] + ((radius * k) / rings) * Math.cos(angle(i)),
    centre[1] + ((radius * k) / rings) * Math.sin(angle(i)),
    top,
  ];
  for (let i = 0; i < segments; i += 1) {
    for (let j = 0; j < rows; j += 1) {
      const [a, b, c, d] = [side(i, j), side(i + 1, j), side(i + 1, j + 1), side(i, j + 1)];
      triangles.push([a, b, c], [a, c, d]);
    }
    for (let k = 0; k < rings; k += 1) {
      const [a, b, c, d] = [disk(k, i), disk(k + 1, i), disk(k + 1, i + 1), disk(k, i + 1)];
      triangles.push([a, b, c]);
      if (k > 0) triangles.push([a, c, d]);
    }
  }
}

/** Write the part to `file`; returns the number of triangles. */
export function writeTestPart(file) {
  const [x, y, z] = PART.plate;
  const triangles = [];
  grid(triangles, [0, 0, z], [x, 0, 0], [0, y, 0], x, y);
  grid(triangles, [0, 0, 0], [0, y, 0], [x, 0, 0], y, x);
  grid(triangles, [0, 0, 0], [x, 0, 0], [0, 0, z], x, z);
  grid(triangles, [0, y, 0], [0, 0, z], [x, 0, 0], z, x);
  grid(triangles, [0, 0, 0], [0, 0, z], [0, y, 0], z, y);
  grid(triangles, [x, 0, 0], [0, y, 0], [0, 0, z], y, z);
  boss(triangles);
  const buffer = Buffer.alloc(84 + triangles.length * 50);
  buffer.write('Mesh-to-CAD user test part', 0, 'ascii');
  buffer.writeUInt32LE(triangles.length, 80);
  triangles.forEach((triangle, index) => {
    const offset = 84 + index * 50 + 12;
    triangle.flat().forEach((value, k) => buffer.writeFloatLE(value, offset + k * 4));
  });
  writeFileSync(file, buffer);
  return triangles.length;
}
