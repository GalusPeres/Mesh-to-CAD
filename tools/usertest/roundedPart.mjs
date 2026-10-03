// The plate for the rounding user test (#24): two D8 buttons whose top edges are
// rounded, and a D10 button whose top is inclined like a direction pad's arm. About
// 0.2 mm triangles on the buttons, like a scan. The plate's top has no triangles under
// the buttons, as a scan has none inside the part.

import { PART, plate, writeStl } from './part.mjs';

/** Where the buttons are, in millimetres (the plate's top is z = 10). */
export const ROUNDED = {
  /** Two D8 buttons, 2 mm high, top edge rounded with `radius`. */
  round: {
    centres: [
      [20, 25],
      [40, 25],
    ],
    radius: 4,
    height: 2,
    rounding: 0.5,
  },
  /** A D10 button, 2 mm high at its centre, its top dropping by `tiltDeg` towards -x. */
  inclined: { centre: [62, 25], radius: 5, height: 2, tiltDeg: 6 },
};

const SEGMENTS = 128;

/** Quads between two rings of points (each `SEGMENTS` long), outward when a is below b. */
function band(triangles, a, b) {
  for (let i = 0; i < SEGMENTS; i += 1) {
    const j = (i + 1) % SEGMENTS;
    triangles.push([a[i], a[j], b[j]], [a[i], b[j], b[i]]);
  }
}

/** A disk filling a ring (a fan from `centre`, counter-clockwise seen from above). */
function cap(triangles, ring, centre) {
  for (let i = 0; i < SEGMENTS; i += 1) triangles.push([centre, ring[i], ring[(i + 1) % SEGMENTS]]);
}

/** A ring around `centre` at `radius`, its height given per point. */
function ring(centre, radius, height) {
  return Array.from({ length: SEGMENTS }, (_, i) => {
    const angle = (2 * Math.PI * i) / SEGMENTS;
    const x = centre[0] + radius * Math.cos(angle);
    const y = centre[1] + radius * Math.sin(angle);
    return [x, y, height(x, y)];
  });
}

/** A round button with a rounded top edge: wall, quarter-circle rounding, top. */
function roundButton(triangles, centre) {
  const { radius, height, rounding } = ROUNDED.round;
  const bottom = PART.plate[2];
  const top = bottom + height;
  const rings = [];
  for (let k = 0; k <= 8; k += 1) {
    rings.push(ring(centre, radius, () => bottom + ((top - rounding - bottom) * k) / 8));
  }
  for (let k = 1; k <= 12; k += 1) {
    const angle = (Math.PI / 2) * (k / 12);
    const r = radius - rounding + rounding * Math.cos(angle);
    rings.push(ring(centre, r, () => top - rounding + rounding * Math.sin(angle)));
  }
  for (let r = radius - rounding - 0.25; r > 0.3; r -= 0.25) rings.push(ring(centre, r, () => top));
  rings.slice(1).forEach((next, index) => band(triangles, rings[index], next));
  cap(triangles, rings.at(-1), [...centre, top]);
}

/** A round button with a sharp-edged inclined top. */
function inclinedButton(triangles) {
  const { centre, radius, height, tiltDeg } = ROUNDED.inclined;
  const bottom = PART.plate[2];
  const slope = Math.tan((tiltDeg * Math.PI) / 180);
  const top = (x) => bottom + height + (x - centre[0]) * slope;
  const rings = [];
  for (let k = 0; k <= 10; k += 1) {
    rings.push(ring(centre, radius, (x) => bottom + ((top(x) - bottom) * k) / 10));
  }
  for (let r = radius - 0.25; r > 0.3; r -= 0.25) rings.push(ring(centre, r, (x) => top(x)));
  rings.slice(1).forEach((next, index) => band(triangles, rings[index], next));
  cap(triangles, rings.at(-1), [...centre, top(centre[0])]);
}

/** The plate's top in 0.5 mm squares, without those under a button. */
function plateTop(triangles) {
  const [length, width, z] = PART.plate;
  const step = 0.5;
  const buttons = [
    ...ROUNDED.round.centres.map((centre) => [centre, ROUNDED.round.radius]),
    [ROUNDED.inclined.centre, ROUNDED.inclined.radius],
  ];
  for (let x = 0; x < length; x += step) {
    for (let y = 0; y < width; y += step) {
      const [a, b, c, d] = [
        [x, y, z],
        [x + step, y, z],
        [x + step, y + step, z],
        [x, y + step, z],
      ];
      // No corner may reach under a button (inside the part).
      const under = buttons.some(([centre, radius]) =>
        [a, b, c, d].some((p) => Math.hypot(p[0] - centre[0], p[1] - centre[1]) < radius + 0.05),
      );
      if (under) continue;
      triangles.push([a, b, c], [a, c, d]);
    }
  }
}

/** Write the part to `file`; returns the number of triangles. */
export function writeRoundedPart(file) {
  const triangles = [];
  plate(triangles, { top: false });
  plateTop(triangles);
  for (const centre of ROUNDED.round.centres) roundButton(triangles, centre);
  inclinedButton(triangles);
  return writeStl(file, triangles);
}
