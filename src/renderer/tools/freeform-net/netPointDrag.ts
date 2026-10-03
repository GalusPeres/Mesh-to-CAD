// Dragging chosen control points of the net. The grabbed surface points follow the
// pointer: with snapping each one lands on the scan where the pointer carries it on
// screen (ray projection, as in QuickSurface), else in the view plane, or along the
// surface normal. The control points move so that their limit
// points get there (controlOffsets), and only the dense rows they influence are
// re-evaluated and re-measured.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import type { LimitSurface } from './limitSurface';
import { type Net, controlOffsets } from './netModel';

/** What a point drag needs of the editor that owns the net. */
export interface PointDragHost {
  readonly viewport: Viewport;
  net(): Net | null;
  /** The limit surface, or null while a kernel job runs (no dragging meanwhile). */
  surface(): LimitSurface | null;
  selection(): ReadonlySet<number>;
  snap(): boolean;
  /** Re-evaluate, re-measure and redraw these dense rows. */
  refreshRows(rows: Uint32Array): void;
  /** Record the current net as a draft history step. */
  record(): void;
  /** The dragged points were let go: true if that joined them to the net (no record). */
  dropped(controls: Uint32Array): boolean;
}

interface Drag {
  controls: Uint32Array;
  rows: Uint32Array;
  startVertices: Float64Array;
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
    const selection = this.host.selection();
    if (!surface || !net || selection.size === 0) return false;
    const controls = Uint32Array.from(selection);
    const startLimits = new Float64Array(controls.length * 3);
    controls.forEach((control, index) => startLimits.set(surface.limitPoint(control), index * 3));
    this.drag = {
      controls,
      rows: surface.rowsOf(controls),
      startVertices: net.vertices.slice(),
      startLimits,
      startScreens: Array.from(controls, (control) =>
        this.host.viewport.worldToScreen(surface.limitPoint(control)),
      ),
    };
    return true;
  }

  /**
   * Move the grabbed surface points: by `offset` in space, or (with snapping and a
   * screen `delta`) onto the scan under each point's screen position moved by `delta`;
   * a point off the scan there moves by `offset`.
   */
  move(offset: Vec3, delta: ScreenPoint | null): void {
    const drag = this.drag;
    const surface = this.host.surface();
    const net = this.host.net();
    if (!drag || !surface || !net) return;
    const onScan = delta !== null && this.host.snap();
    const wanted = new Float64Array(drag.controls.length * 3);
    drag.controls.forEach((_, index) => {
      const o = index * 3;
      const start: Vec3 = [
        drag.startLimits[o] ?? 0,
        drag.startLimits[o + 1] ?? 0,
        drag.startLimits[o + 2] ?? 0,
      ];
      let target: Vec3 = [start[0] + offset[0], start[1] + offset[1], start[2] + offset[2]];
      const screen = drag.startScreens[index];
      if (onScan && screen) {
        const at = { x: screen.x + delta.x, y: screen.y + delta.y };
        const hit = this.host.viewport.pick(at, { kinds: ['scan'] });
        if (hit?.kind === 'scan') target = hit.point;
      }
      wanted.set([target[0] - start[0], target[1] - start[1], target[2] - start[2]], o);
    });
    const offsets = controlOffsets(surface, drag.controls, wanted);
    net.vertices.set(drag.startVertices);
    drag.controls.forEach((control, index) => {
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
      if (!this.host.dropped(drag.controls)) this.host.record();
      return;
    }
    net.vertices.set(drag.startVertices);
    this.host.refreshRows(drag.rows);
  }

  get active(): boolean {
    return this.drag !== null;
  }
}
