// The synthetic parts the user tests run on, written as binary STL with about 1 mm
// triangles, so every position is known in advance: a plate with a round boss, and a
// plate with buttons whose outlines are no whole template (for Formen erkennen).

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

/** The six sides of the plate (from the origin, outward normals). */
function plate(triangles) {
  const [x, y, z] = PART.plate;
  grid(triangles, [0, 0, z], [x, 0, 0], [0, y, 0], x, y);
  grid(triangles, [0, 0, 0], [0, y, 0], [x, 0, 0], y, x);
  grid(triangles, [0, 0, 0], [x, 0, 0], [0, 0, z], x, z);
  grid(triangles, [0, y, 0], [0, 0, z], [x, 0, 0], z, x);
  grid(triangles, [0, 0, 0], [0, 0, z], [0, y, 0], z, y);
  grid(triangles, [x, 0, 0], [0, y, 0], [0, 0, z], y, z);
}

/** Write the part to `file`; returns the number of triangles. */
export function writeTestPart(file) {
  const triangles = [];
  plate(triangles);
  boss(triangles);
  return writeStl(file, triangles);
}

/** The plate for Formen erkennen: buttons 2 mm high on its top (z = 10). */
export const BUTTONS = {
  top: 12,
  /** A D8 button at the right end, cut by the end face x = 80, 2 mm beyond its centre. */
  cut: { centre: [78, 25], radius: 4 },
  /** A whole D8 button. */
  whole: { centre: [60, 25], radius: 4 },
  /** A keyhole: a D10 button with a 4 mm wide tail to x = 40 (one arc, three lines). */
  keyhole: { centre: [25, 25], radius: 5, tail: 40, width: 4 },
};

/** Points along an arc (radians), both ends included. */
function arc(centre, radius, from, to, step = Math.PI / 32) {
  const count = Math.max(2, Math.ceil(Math.abs(to - from) / step));
  return Array.from({ length: count + 1 }, (_, i) => {
    const angle = from + ((to - from) * i) / count;
    return [centre[0] + radius * Math.cos(angle), centre[1] + radius * Math.sin(angle)];
  });
}

/** A straight-walled button on the plate: its counter-clockwise outline (closed by its
 * last point back to the first) is walled up from the plate and capped by a fan from
 * `centre`, which sees the whole outline. */
function button(triangles, outline, centre) {
  const bottom = PART.plate[2];
  const top = BUTTONS.top;
  outline.forEach((a, i) => {
    const b = outline[(i + 1) % outline.length];
    if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9) return;
    const rows = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1])));
    grid(triangles, [...a, bottom], [b[0] - a[0], b[1] - a[1], 0], [0, 0, top - bottom], rows, 2);
    triangles.push([
      [...centre, top],
      [...a, top],
      [...b, top],
    ]);
  });
}

/** Write the buttons plate to `file`; returns the number of triangles. */
export function writeButtonsPart(file) {
  const triangles = [];
  plate(triangles);
  const { cut, whole, keyhole } = BUTTONS;
  const reach = Math.acos((PART.plate[0] - cut.centre[0]) / cut.radius);
  button(triangles, arc(cut.centre, cut.radius, reach, 2 * Math.PI - reach), cut.centre);
  button(triangles, arc(whole.centre, whole.radius, 0, 2 * Math.PI).slice(0, -1), whole.centre);
  const half = keyhole.width / 2;
  const meet = Math.asin(half / keyhole.radius);
  const cy = keyhole.centre[1];
  button(
    triangles,
    [
      ...arc(keyhole.centre, keyhole.radius, meet, 2 * Math.PI - meet),
      [keyhole.tail, cy - half],
      [keyhole.tail, cy + half],
    ],
    keyhole.centre,
  );
  return writeStl(file, triangles);
}

function writeStl(file, triangles) {
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
