// Placing a new face of the net on the scan, as QuickSurface's "Add face" (four
// clicked corners in order) and "Rectangular face" (two clicked corners of a rectangle
// on screen, whose four corners are projected onto the scan). The face is turned to
// the outside of the scan (by the scan normals at its corners).

import type { ScreenPoint, Vec3 } from '../../viewport/api';

/** A corner on the scan with the scan's outward normal there. */
export interface ScanCorner {
  point: Vec3;
  normal: Vec3;
  /** The existing net point the corner snapped to (the face docks on there). */
  vertex?: number;
}

export type FaceMode = 'quad' | 'rectangle';

export class FacePlacement {
  private clicked: ScanCorner[] = [];
  private pointer: ScanCorner | null = null;
  private rectangle: Vec3[] | null = null;
  active = false;
  mode: FaceMode = 'quad';
  /** The first corner of a rectangle on screen, once clicked. */
  anchor: ScreenPoint | null = null;

  /** Start or stop placing (forgets the corners clicked so far). */
  set(active: boolean, mode: FaceMode): void {
    this.active = active;
    this.mode = mode;
    this.clicked = [];
    this.pointer = null;
    this.rectangle = null;
    this.anchor = null;
  }

  /** Corners clicked so far. */
  get count(): number {
    return this.mode === 'rectangle' ? (this.anchor ? 1 : 0) : this.clicked.length;
  }

  /** Add a clicked corner; the four corners once the face is complete, else null. */
  click(corner: ScanCorner): ScanCorner[] | null {
    this.clicked.push(corner);
    return this.clicked.length === 4 ? [...this.clicked] : null;
  }

  /** Take back the last clicked corner; false if there was none. */
  undo(): boolean {
    if (this.anchor) {
      this.anchor = null;
      this.rectangle = null;
      return true;
    }
    return this.clicked.pop() !== undefined;
  }

  /** The corner under the pointer (rubber band to the next corner), or null. */
  hover(corner: ScanCorner | null): void {
    this.pointer = corner;
  }

  /** The rectangle face to the pointer (its corners on the scan), or null. */
  hoverRectangle(corners: Vec3[] | null): void {
    this.rectangle = corners;
  }

  /** Guide lines, corner points, and the net points the face will dock on. */
  preview(): { segments: number[]; points: number[]; joins: number[] } {
    const segments: number[] = [];
    const points: number[] = [];
    const joins: number[] = [];
    if (!this.active) return { segments, points, joins };
    const pointer = this.pointer;
    for (const corner of [...this.clicked, ...(pointer ? [pointer] : [])])
      if (corner.vertex !== undefined) joins.push(...corner.point);
    const corners = this.rectangle ?? this.clicked.map((corner) => corner.point);
    if (!this.rectangle && pointer && this.mode === 'quad') corners.push(pointer.point);
    if (!this.rectangle && pointer && this.mode === 'rectangle') points.push(...pointer.point);
    corners.forEach((corner, i) => {
      points.push(...corner);
      const next = corners[i + 1] ?? (corners.length === 4 ? corners[0] : undefined);
      if (next) segments.push(...corner, ...next);
    });
    return { segments, points, joins };
  }
}

/** The summed normal of a face's corners: the side its quad must face. */
export function outwardOf(corners: readonly ScanCorner[]): Vec3 {
  return corners.reduce<Vec3>(
    (sum, { normal: n }) => [sum[0] + n[0], sum[1] + n[1], sum[2] + n[2]],
    [0, 0, 0],
  );
}
