// The section outline: where the displayed scan triangles cross the section plane.

/**
 * Line segments (6 floats each) where triangles cross the plane n . x = d.
 * `positions` holds 9 floats per face; `skip(face)` leaves out hidden faces.
 */
export function sectionSegments(
  positions: Float32Array,
  normal: readonly [number, number, number],
  offset: number,
  skip: (face: number) => boolean = () => false,
): Float32Array {
  const [nx, ny, nz] = normal;
  const faceCount = positions.length / 9;
  const out: number[] = [];
  const distance = [0, 0, 0];
  for (let face = 0; face < faceCount; face += 1) {
    const base = face * 9;
    let above = 0;
    for (let corner = 0; corner < 3; corner += 1) {
      const o = base + corner * 3;
      const value =
        (positions[o] ?? 0) * nx + (positions[o + 1] ?? 0) * ny + (positions[o + 2] ?? 0) * nz - offset;
      distance[corner] = value;
      if (value > 0) above += 1;
    }
    if (above === 0 || above === 3 || skip(face)) continue;
    for (let corner = 0; corner < 3; corner += 1) {
      const next = (corner + 1) % 3;
      const a = distance[corner] ?? 0;
      const b = distance[next] ?? 0;
      if (a > 0 === b > 0) continue;
      const t = a / (a - b);
      const oa = base + corner * 3;
      const ob = base + next * 3;
      for (let axis = 0; axis < 3; axis += 1) {
        const pa = positions[oa + axis] ?? 0;
        out.push(pa + ((positions[ob + axis] ?? 0) - pa) * t);
      }
    }
  }
  return Float32Array.from(out);
}
