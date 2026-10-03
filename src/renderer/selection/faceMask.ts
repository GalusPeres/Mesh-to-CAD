// Operations on per-face byte masks (1 = set). Every operation that changes a
// mask returns the faces it actually changed, so callers can update the
// viewport incrementally and record exact undo information.

/** Set the faces to `value`; returns the faces whose state changed. */
export function setFaces(mask: Uint8Array, faces: ArrayLike<number>, value: 0 | 1): Uint32Array {
  const changed = new Uint32Array(faces.length);
  let count = 0;
  for (let index = 0; index < faces.length; index += 1) {
    const face = faces[index] ?? -1;
    if (face < 0 || face >= mask.length || mask[face] === value) continue;
    mask[face] = value;
    changed[count] = face;
    count += 1;
  }
  return changed.slice(0, count);
}

/** Indices of the set faces, ascending. */
export function facesOf(mask: Uint8Array): Uint32Array {
  let count = 0;
  for (const value of mask) if (value) count += 1;
  const faces = new Uint32Array(count);
  let next = 0;
  for (let face = 0; face < mask.length; face += 1) {
    if (mask[face]) {
      faces[next] = face;
      next += 1;
    }
  }
  return faces;
}

export function countSet(mask: Uint8Array | null): number {
  if (!mask) return 0;
  let count = 0;
  for (const value of mask) if (value) count += 1;
  return count;
}

/** Faces that are not hidden and not yet selected (select all visible / invert). */
export function unselectedVisible(selection: Uint8Array, hidden: Uint8Array | null): Uint32Array {
  const faces: number[] = [];
  for (let face = 0; face < selection.length; face += 1) {
    if (!selection[face] && !hidden?.[face]) faces.push(face);
  }
  return Uint32Array.from(faces);
}

/**
 * Faces one ring outside the selection: unselected, visible neighbours of
 * selected faces. `neighbours` holds three entries per face (-1 = open edge).
 */
export function outerRing(
  selection: Uint8Array,
  neighbours: Int32Array,
  hidden: Uint8Array | null,
): Uint32Array {
  const ring = new Uint8Array(selection.length);
  const faces: number[] = [];
  for (let face = 0; face < selection.length; face += 1) {
    if (!selection[face]) continue;
    for (let slot = 0; slot < 3; slot += 1) {
      const other = neighbours[face * 3 + slot] ?? -1;
      if (other < 0 || selection[other] || ring[other] || hidden?.[other]) continue;
      ring[other] = 1;
      faces.push(other);
    }
  }
  return Uint32Array.from(faces).sort();
}

/**
 * Selected faces on the border of the selection: at least one neighbour across
 * an edge is not selected. Open mesh edges do not count as a border.
 */
export function innerRing(selection: Uint8Array, neighbours: Int32Array): Uint32Array {
  const faces: number[] = [];
  for (let face = 0; face < selection.length; face += 1) {
    if (!selection[face]) continue;
    for (let slot = 0; slot < 3; slot += 1) {
      const other = neighbours[face * 3 + slot] ?? -1;
      if (other >= 0 && !selection[other]) {
        faces.push(face);
        break;
      }
    }
  }
  return Uint32Array.from(faces);
}

/** Faces whose value differs between the masks, split by direction. */
export function diffMasks(
  before: Uint8Array,
  after: Uint8Array,
): { added: Uint32Array; removed: Uint32Array } {
  const added: number[] = [];
  const removed: number[] = [];
  for (let face = 0; face < after.length; face += 1) {
    const was = before[face] ?? 0;
    const is = after[face] ?? 0;
    if (was === is) continue;
    (is ? added : removed).push(face);
  }
  return { added: Uint32Array.from(added), removed: Uint32Array.from(removed) };
}
