import { writeFileSync } from 'node:fs';

/**
 * Write a closed torus as binary STL: `2 * around * tube` triangles.
 * 250 x 100 gives 50 000 triangles.
 */
export function writeTorusStl(
  file: string,
  around = 250,
  tube = 100,
  major = 30,
  minor = 10,
): number {
  const point = (i: number, j: number): [number, number, number] => {
    const u = (2 * Math.PI * (i % around)) / around;
    const v = (2 * Math.PI * (j % tube)) / tube;
    const ring = major + minor * Math.cos(v);
    return [ring * Math.cos(u), ring * Math.sin(u), minor * Math.sin(v)];
  };
  const triangles: [number, number, number][][] = [];
  for (let i = 0; i < around; i += 1) {
    for (let j = 0; j < tube; j += 1) {
      const a = point(i, j);
      const b = point(i + 1, j);
      const c = point(i + 1, j + 1);
      const d = point(i, j + 1);
      triangles.push([a, b, c], [a, c, d]);
    }
  }
  const buffer = Buffer.alloc(84 + triangles.length * 50);
  buffer.write('Mesh-to-CAD end-to-end test torus', 0, 'ascii');
  buffer.writeUInt32LE(triangles.length, 80);
  triangles.forEach((triangle, index) => {
    const offset = 84 + index * 50 + 12;
    triangle
      .flat()
      .forEach((value, component) => buffer.writeFloatLE(value, offset + component * 4));
  });
  writeFileSync(file, buffer);
  return triangles.length;
}
