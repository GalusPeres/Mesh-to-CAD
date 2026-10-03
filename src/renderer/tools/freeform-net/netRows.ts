// New rows dragged out of the net's border by drag and drop, as QuickSurface
// duplicates edges: every point of the dragged border runs goes where the pointer
// carries it on screen and lands on the scan under it (ray projection), so a row
// follows the part over edges and roundings wherever it is dropped. Dropped onto a
// border point of the net, a point joins it instead, which bridges two pieces.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import { type RowTarget, joinsPoint } from './netBuild';
import type { Net } from './netModel';
import { type Edge, borderEdges } from './netTopology';

/** A dropped point this close to a border point of the net (on screen) joins it. */
export const JOIN_RADIUS_PX = 12;

/** What the row drag needs of the editor that owns the net. */
export interface RowHost {
  readonly viewport: Viewport;
  net(): Net | null;
  limitPoint(control: number): Vec3;
  /** Screen position of a control point, or null if it faces away from the viewer. */
  screenOf(control: number): ScreenPoint | null;
  snap(): boolean;
}

interface Start {
  screen: ScreenPoint;
  origin: Vec3;
  /** View direction there: without a scan hit the point moves in the view plane. */
  normal: Vec3;
}

interface Rows {
  runs: Edge[][];
  starts: Map<number, Start>;
  /** Border points of the rest of the net that a dropped point may join. */
  joinable: { vertex: number; screen: ScreenPoint }[];
  targets: Map<number, RowTarget>;
}

const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** The border point nearest to `at` on screen within the join radius, or null. */
export function nearestJoin(
  joinable: readonly { vertex: number; screen: ScreenPoint }[],
  at: ScreenPoint,
  taken: ReadonlySet<number> = new Set(),
): number | null {
  let best: number | null = null;
  let bestDistance = JOIN_RADIUS_PX;
  for (const { vertex, screen } of joinable) {
    const distance = Math.hypot(screen.x - at.x, screen.y - at.y);
    if (distance < bestDistance && !taken.has(vertex)) {
      best = vertex;
      bestDistance = distance;
    }
  }
  return best;
}

/** Border points of a net with their screen positions, except `skip`. */
export function joinableBorder(
  net: Net,
  screenOf: (control: number) => ScreenPoint | null,
  skip: ReadonlySet<number>,
): { vertex: number; screen: ScreenPoint }[] {
  const vertices = new Set(borderEdges(net).flatMap(({ a, b }) => [a, b]));
  const joinable: { vertex: number; screen: ScreenPoint }[] = [];
  for (const vertex of vertices) {
    const screen = skip.has(vertex) ? null : screenOf(vertex);
    if (screen) joinable.push({ vertex, screen });
  }
  return joinable;
}

export class RowDrag {
  private rows: Rows | null = null;

  constructor(private readonly host: RowHost) {}

  get active(): boolean {
    return this.rows !== null;
  }

  /** Start dragging rows out of these border runs; false if one is off screen. */
  begin(runs: Edge[][]): boolean {
    const net = this.host.net();
    if (!net || runs.length === 0) return false;
    const starts = new Map<number, Start>();
    for (const { a, b } of runs.flat()) {
      for (const vertex of [a, b]) {
        if (starts.has(vertex)) continue;
        const origin = this.host.limitPoint(vertex);
        const screen = this.host.viewport.worldToScreen(origin);
        if (!screen) return false;
        const normal = this.host.viewport.screenToRay(screen).direction;
        starts.set(vertex, { screen, origin, normal });
      }
    }
    const joinable = joinableBorder(net, (v) => this.host.screenOf(v), new Set(starts.keys()));
    this.rows = { runs, starts, joinable, targets: new Map() };
    return true;
  }

  /** The pointer moved by `delta` (screen pixels) since the drag began. */
  move(delta: ScreenPoint): void {
    const rows = this.rows;
    if (!rows) return;
    const taken = new Set<number>();
    for (const [vertex, start] of rows.starts) {
      const at = { x: start.screen.x + delta.x, y: start.screen.y + delta.y };
      const join = nearestJoin(rows.joinable, at, taken);
      if (join !== null) taken.add(join);
      rows.targets.set(vertex, join !== null ? { onto: join } : this.place(start, at));
    }
  }

  /** End the drag: the runs and where their points go, or null if nothing moved. */
  finish(): { runs: Edge[][]; target: (vertex: number) => RowTarget } | null {
    const rows = this.rows;
    this.rows = null;
    if (!rows || rows.targets.size === 0) return null;
    return {
      runs: rows.runs,
      target: (vertex) => rows.targets.get(vertex) ?? this.host.limitPoint(vertex),
    };
  }

  cancel(): void {
    this.rows = null;
  }

  /** The rows being dragged as line segments, and the border points they will join. */
  preview(): { segments: number[]; points: number[] } {
    const rows = this.rows;
    const segments: number[] = [];
    const points: number[] = [];
    if (!rows || rows.targets.size === 0) return { segments, points };
    const point = (vertex: number) => this.host.limitPoint(vertex);
    const where = (vertex: number): Vec3 => {
      const target = rows.targets.get(vertex);
      if (!target) return point(vertex);
      return joinsPoint(target) ? point(target.onto) : target;
    };
    for (const { a, b } of rows.runs.flat()) {
      const [qa, qb] = [where(a), where(b)];
      segments.push(...point(a), ...qa, ...qa, ...qb, ...qb, ...point(b));
    }
    for (const target of rows.targets.values())
      if (joinsPoint(target)) points.push(...point(target.onto));
    return { segments, points };
  }

  /** Where a row point lands for the pointer at `at`: on the scan under it. */
  private place(start: Start, at: ScreenPoint): Vec3 {
    const { viewport } = this.host;
    if (this.host.snap()) {
      const hit = viewport.pick(at, { kinds: ['scan'] });
      if (hit?.kind === 'scan') return hit.point;
    }
    // Off the scan, or without snapping: in the view plane through the point.
    const ray = viewport.screenToRay(at);
    const denominator = dot(start.normal, ray.direction);
    if (Math.abs(denominator) < 1e-9) return start.origin;
    const toOrigin: Vec3 = [
      start.origin[0] - ray.origin[0],
      start.origin[1] - ray.origin[1],
      start.origin[2] - ray.origin[2],
    ];
    const s = dot(start.normal, toOrigin) / denominator;
    return [
      ray.origin[0] + ray.direction[0] * s,
      ray.origin[1] + ray.direction[1] * s,
      ray.origin[2] + ray.direction[2] * s,
    ];
  }
}
