// Binary STL out of a list of triangles (three [x, y, z] corners each, outward wound).

import { writeFileSync } from 'node:fs';

/** Write the triangles to `file`; returns their number. */
export function writeBinaryStl(file, triangles, header) {
  const buffer = Buffer.alloc(84 + triangles.length * 50);
  buffer.write(header, 0, 'ascii');
  buffer.writeUInt32LE(triangles.length, 80);
  triangles.forEach((triangle, index) => {
    const offset = 84 + index * 50 + 12;
    triangle.flat().forEach((value, k) => buffer.writeFloatLE(value, offset + k * 4));
  });
  writeFileSync(file, buffer);
  return triangles.length;
}
