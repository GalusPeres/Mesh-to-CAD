// What lies under the pointer in the freeform-net tool: control points and net edges
// on screen (front-facing ones only, so the far side of a part cannot be grabbed),
// and the scan point with its outward normal.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import type { Edge } from './netTopology';
import type { NetEditor } from './netEditor';

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
}

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
