// Placing a new face of the net on the scan, as QuickSurface's "Add face" (four
// clicked corners in order) and "Rectangular face" (two clicked corners of a rectangle
// on screen, whose four corners are projected onto the scan). The face is turned to
// the outside of the scan (by the scan normals at its corners).

import type { ScreenPoint, Vec3 } from '../../viewport/api';

/** A corner on the scan with the scan's outward normal there. */
export interface ScanCorner {
  point: Vec3;
  normal: Vec3;
}

export type FaceMode = 'quad' | 'rectangle';

export class FacePlacement {
  private clicked: ScanCorner[] = [];
  private pointer: Vec3 | null = null;
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

  /** The scan point under the pointer (rubber band to the next corner), or null. */
  hover(point: Vec3 | null): void {
    this.pointer = point;
  }

  /** The rectangle face to the pointer (its corners on the scan), or null. */
  hoverRectangle(corners: Vec3[] | null): void {
    this.rectangle = corners;
  }

  /** Guide lines and corner points to draw. */
  preview(): { segments: number[]; points: number[] } {
    const segments: number[] = [];
    const points: number[] = [];
    if (!this.active) return { segments, points };
    const corners = this.rectangle ?? this.clicked.map((corner) => corner.point);
    if (!this.rectangle && this.pointer && this.mode === 'quad') corners.push(this.pointer);
    if (!this.rectangle && this.pointer && this.mode === 'rectangle') points.push(...this.pointer);
    corners.forEach((corner, i) => {
      points.push(...corner);
      const next = corners[i + 1] ?? (corners.length === 4 ? corners[0] : undefined);
      if (next) segments.push(...corner, ...next);
    });
    return { segments, points };
  }
}

/** The summed normal of a face's corners: the side its quad must face. */
export function outwardOf(corners: readonly ScanCorner[]): Vec3 {
  return corners.reduce<Vec3>(
    (sum, { normal: n }) => [sum[0] + n[0], sum[1] + n[1], sum[2] + n[2]],
    [0, 0, 0],
  );
}
