// Dragging chosen control points of the net. The grabbed surface points follow the
// pointer, slowed down by the drag strength: with snapping each one lands on the scan
// where the pointer carries it on screen (ray projection, as in QuickSurface), else in
// the view plane, or along the surface normal. The control points move so that their
// limit points get there while pinned points (and, if asked, the neighbours) hold
// still (netDragSolve), and only the dense rows they influence are re-evaluated.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import type { LimitSurface } from './limitSurface';
import { type DragSet, dragOffsets, dragSet } from './netDragSolve';
import type { Net } from './netModel';

/** What a point drag needs of the editor that owns the net. */
export interface PointDragHost {
  readonly viewport: Viewport;
  net(): Net | null;
  /** The limit surface, or null while a kernel job runs (no dragging meanwhile). */
  surface(): LimitSurface | null;
  selection(): ReadonlySet<number>;
  pinned(): ReadonlySet<number>;
  snap(): boolean;
  /** Hold the limit points next to the dragged ones ("Don't move neighbours"). */
  keepNeighbours(): boolean;
  /** Share of the pointer's movement the points follow (1 = all of it). */
  strength(): number;
  /** Re-evaluate, re-measure and redraw these dense rows. */
  refreshRows(rows: Uint32Array): void;
  /** Record the current net as a draft history step. */
  record(): void;
  /** The dragged points were let go: true if that joined them to the net (no record). */
  dropped(controls: Uint32Array): boolean;
}

interface Drag {
  set: DragSet;
  rows: Uint32Array;
  startVertices: Float64Array;
  /** Limit points of the dragged control points at the start. */
  startLimits: Float64Array;
  /** Screen positions of the grabbed surface points (null off screen). */
  startScreens: (ScreenPoint | null)[];
}

export class NetPointDrag {
  private drag: Drag | null = null;

  constructor(private readonly host: PointDragHost) {}

  /** Start moving the chosen control points; false if nothing can be dragged now. */
  begin(): boolean {
    const surface = this.host.surface();
    const net = this.host.net();
    if (!surface || !net) return false;
    const set = dragSet(
      surface,
      this.host.selection(),
      this.host.pinned(),
      this.host.keepNeighbours(),
    );
    if (set.dragged === 0) return false;
    const dragged = set.controls.subarray(0, set.dragged);
    const startLimits = new Float64Array(set.dragged * 3);
    dragged.forEach((control, index) => startLimits.set(surface.limitPoint(control), index * 3));
    this.drag = {
      set,
      rows: surface.rowsOf(set.controls),
      startVertices: net.vertices.slice(),
      startLimits,
      startScreens: Array.from(dragged, (control) =>
        this.host.viewport.worldToScreen(surface.limitPoint(control)),
      ),
    };
    return true;
  }

  /**
   * Move the grabbed surface points: by `offset` in space, or (with snapping and a
   * screen `delta`) onto the scan under each point's screen position moved by `delta`;
   * a point off the scan there moves by `offset`. Both are scaled by the strength.
   */
  move(offset: Vec3, delta: ScreenPoint | null): void {
    const drag = this.drag;
    const surface = this.host.surface();
    const net = this.host.net();
    if (!drag || !surface || !net) return;
    const strength = this.host.strength();
    const onScan = delta !== null && this.host.snap();
    const moves = new Float64Array(drag.set.dragged * 3);
    for (let index = 0; index < drag.set.dragged; index += 1) {
      const o = index * 3;
      const start: Vec3 = [
        drag.startLimits[o] ?? 0,
        drag.startLimits[o + 1] ?? 0,
        drag.startLimits[o + 2] ?? 0,
      ];
      let move: Vec3 = [offset[0] * strength, offset[1] * strength, offset[2] * strength];
      const screen = drag.startScreens[index];
      if (onScan && screen) {
        const at = { x: screen.x + delta.x * strength, y: screen.y + delta.y * strength };
        const hit = this.host.viewport.pick(at, { kinds: ['scan'] });
        if (hit?.kind === 'scan')
          move = [hit.point[0] - start[0], hit.point[1] - start[1], hit.point[2] - start[2]];
      }
      moves.set(move, o);
    }
    const offsets = dragOffsets(surface, drag.set, moves);
    net.vertices.set(drag.startVertices);
    drag.set.controls.forEach((control, index) => {
      for (let axis = 0; axis < 3; axis += 1) {
        const c = control * 3 + axis;
        net.vertices[c] = (drag.startVertices[c] ?? 0) + (offsets[index * 3 + axis] ?? 0);
      }
    });
    this.host.refreshRows(drag.rows);
  }

  /** Finish the drag: keep it (a draft history step) or put the points back. */
  end(keep: boolean): void {
    const drag = this.drag;
    const net = this.host.net();
    this.drag = null;
    if (!drag || !net) return;
    if (keep) {
      if (!this.host.dropped(drag.set.controls.subarray(0, drag.set.dragged))) this.host.record();
      return;
    }
    net.vertices.set(drag.startVertices);
    this.host.refreshRows(drag.rows);
  }

  get active(): boolean {
    return this.drag !== null;
  }
}
