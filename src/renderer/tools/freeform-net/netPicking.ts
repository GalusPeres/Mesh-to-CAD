// What lies under the pointer in the freeform-net tool: control points and net edges
// on screen (front-facing ones only, so the far side of a part cannot be grabbed), the
// scan point with its outward normal, a screen rectangle's corners on the scan, and
// the offset a drag in the view plane (or along a normal) gives a grabbed point.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import type { NetEditor } from './netEditor';
import type { ScanCorner } from './netFacePlacement';
import type { Edge } from './netTopology';

/** A plane a drag moves in: through the grabbed point, facing the viewer. */
export interface DragPlane {
  origin: Vec3;
  normal: Vec3;
}

const PICK_RADIUS_PX = 10;
/** Control points within this distance of the pointer are drawn. */
const NEARBY_RADIUS_PX = 150;
/** An edge within this distance of the pointer is under it. */
const EDGE_RADIUS_PX = 7;
export interface NetPicking {
  /** The pickable control point under the pointer, and the visible ones around it. */
  pointsAt(at: ScreenPoint): { picked: number | null; nearby: number[] };
  /** The visible net edge under the pointer, with whether it is open border. */
  edgeAt(at: ScreenPoint): { edge: Edge; border: boolean } | null;
  /** The scan point under the pointer and the scan's outward normal there. */
  scanAt(at: ScreenPoint): { point: Vec3; normal: Vec3 } | null;
  /** Visible control points inside a screen rectangle. */
  pointsInBox(from: ScreenPoint, to: ScreenPoint): number[];
  /** The four corners of a screen rectangle on the scan, or null if one misses it. */
  rectangleOnScan(from: ScreenPoint, to: ScreenPoint): ScanCorner[] | null;
  /** The view plane through a point. */
  viewPlane(origin: Vec3): DragPlane;
  /**
   * How far a point grabbed on `plane` moves for the pointer at `at`: in the plane, or
   * along `normal` (the closest point of that line to the pointer ray).
   */
  dragOffset(at: ScreenPoint, plane: DragPlane, normal: Vec3 | null): Vec3 | null;
}

const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** Distance of a point to the segment a-b on screen. */
function segmentDistance(at: ScreenPoint, a: ScreenPoint, b: ScreenPoint): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = dx * dx + dy * dy;
  const t =
    length > 0 ? Math.max(0, Math.min(1, ((at.x - a.x) * dx + (at.y - a.y) * dy) / length)) : 0;
  return Math.hypot(at.x - (a.x + t * dx), at.y - (a.y + t * dy));
}

export function createNetPicking(editor: NetEditor, viewport: Viewport): NetPicking {
  const screenOf = (control: number) => editor.visibleScreen(control);

  const visiblePoints = function* (): Generator<{ control: number; screen: ScreenPoint }> {
    for (let control = 0; control < editor.controlCount; control += 1) {
      const screen = screenOf(control);
      if (screen) yield { control, screen };
    }
  };

  return {
    pointsAt(at) {
      let picked: number | null = null;
      let bestDistance = PICK_RADIUS_PX;
      const nearby: number[] = [];
      for (const { control, screen } of visiblePoints()) {
        const distance = Math.hypot(screen.x - at.x, screen.y - at.y);
        if (distance <= NEARBY_RADIUS_PX) nearby.push(control);
        if (distance <= bestDistance) {
          picked = control;
          bestDistance = distance;
        }
      }
      return { picked, nearby };
    },

    edgeAt(at) {
      const edges = editor.edges;
      if (!edges) return null;
      const screens = new Map<number, ScreenPoint | null>();
      const cached = (control: number): ScreenPoint | null => {
        if (!screens.has(control)) screens.set(control, screenOf(control));
        return screens.get(control) ?? null;
      };
      let best: { edge: Edge; border: boolean } | null = null;
      let bestDistance = EDGE_RADIUS_PX;
      for (let index = 0; index < edges.pairs.length / 2; index += 1) {
        const a = edges.pairs[index * 2] ?? 0;
        const b = edges.pairs[index * 2 + 1] ?? 0;
        const sa = cached(a);
        const sb = cached(b);
        if (!sa || !sb) continue;
        const distance = segmentDistance(at, sa, sb);
        if (distance < bestDistance) {
          bestDistance = distance;
          const border = (edges.border[index] ?? 0) !== 0;
          best = { edge: (border && editor.borderEdge(a, b)) || { a, b }, border };
        }
      }
      return best;
    },

    scanAt(at) {
      const hit = viewport.pick(at, { kinds: ['scan'] });
      if (!hit || hit.kind !== 'scan') return null;
      const ray = viewport.screenToRay(at);
      const normal = viewport.scanSurface.closest(hit.point, 1)?.normal ?? [
        -ray.direction[0],
        -ray.direction[1],
        -ray.direction[2],
      ];
      return { point: hit.point, normal };
    },

    rectangleOnScan(from, to) {
      const corners = [from, { x: to.x, y: from.y }, to, { x: from.x, y: to.y }].map((at) =>
        this.scanAt(at),
      );
      const onScan = corners.filter((corner): corner is ScanCorner => corner !== null);
      return onScan.length === 4 ? onScan : null;
    },

    viewPlane(origin) {
      const at = viewport.worldToScreen(origin);
      return { origin, normal: at ? viewport.screenToRay(at).direction : [0, 0, 1] };
    },

    dragOffset(at, plane, normal) {
      const ray = viewport.screenToRay(at);
      const w0: Vec3 = [
        plane.origin[0] - ray.origin[0],
        plane.origin[1] - ray.origin[1],
        plane.origin[2] - ray.origin[2],
      ];
      if (normal) {
        const b = dot(normal, ray.direction);
        const denominator = 1 - b * b;
        if (Math.abs(denominator) < 1e-6) return null;
        const t = (b * dot(ray.direction, w0) - dot(normal, w0)) / denominator;
        return [normal[0] * t, normal[1] * t, normal[2] * t];
      }
      const denominator = dot(plane.normal, ray.direction);
      if (Math.abs(denominator) < 1e-9) return null;
      const s = dot(plane.normal, w0) / denominator;
      return [
        ray.origin[0] + ray.direction[0] * s - plane.origin[0],
        ray.origin[1] + ray.direction[1] * s - plane.origin[1],
        ray.origin[2] + ray.direction[2] * s - plane.origin[2],
      ];
    },

    pointsInBox(from, to) {
      const [minX, maxX] = [Math.min(from.x, to.x), Math.max(from.x, to.x)];
      const [minY, maxY] = [Math.min(from.y, to.y), Math.max(from.y, to.y)];
      const inside: number[] = [];
      for (const { control, screen } of visiblePoints()) {
        if (screen.x >= minX && screen.x <= maxX && screen.y >= minY && screen.y <= maxY)
          inside.push(control);
      }
      return inside;
    },
  };
}
