// Pointer handling of the freeform-net tool: hover and pick control points in
// screen space, drag them (in the view plane, or along the surface normal with Alt),
// and choose points with a rectangle. Building by hand: while placing a face, clicks
// on the scan set its corners; dragging a border edge adds a row of quads (with
// Shift the whole border chain); S over an edge splits the ring of quads crossing
// it. Rows grow outward along the surface, so they follow it over edges and fillets
// (Ctrl+Shift grows the border sides that face the drag, around the corner between
// them: drag towards a corner of the part to wrap the net round it). Empty-space
// gestures are left to an active selection mode, so triangles can
// still be selected while the tool is open.

import type { ScreenPoint, Vec3, Viewport, ViewportInteraction } from '../../viewport/api';
import type { Edge } from './netBuild';
import type { NetEditor } from './netEditor';

const PICK_RADIUS_PX = 10;
/** Control points within this distance of the pointer are drawn. */
const NEARBY_RADIUS_PX = 150;
const DRAG_THRESHOLD_PX = 3;
/** An edge within this distance of the pointer is under it. */
const EDGE_RADIUS_PX = 7;
/** Points whose surface faces away from the viewer more than this are not pickable. */
const FACING_LIMIT = 0.15;

export interface BoxRectangle {
  from: ScreenPoint;
  to: ScreenPoint;
}

export interface NetInteractionHooks {
  /** Draw (or clear) the selection rectangle. */
  onBox(rectangle: BoxRectangle | null): void;
  /** A triangle selection mode (brush, lasso, ...) is active. */
  selectionModeActive(): boolean;
}

type Gesture =
  | {
      kind: 'point';
      control: number;
      start: ScreenPoint;
      mode: 'replace' | 'add' | 'remove';
      moved: boolean;
      plane: { origin: Vec3; normal: Vec3 };
    }
  | { kind: 'box'; start: ScreenPoint; mode: 'replace' | 'add' | 'remove' }
  | {
      kind: 'edge';
      edge: Edge;
      /** Grow the sides facing the drag (Ctrl+Shift) instead of a fixed chain. */
      facing: boolean;
      chain: Edge[];
      start: ScreenPoint;
      moved: boolean;
      plane: { origin: Vec3; normal: Vec3 };
      outward: Vec3;
      distance: number;
    };

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const add = (a: Vec3, b: Vec3, scale = 1): Vec3 => [
  a[0] + b[0] * scale,
  a[1] + b[1] * scale,
  a[2] + b[2] * scale,
];

/** Distance of a point to the segment a-b on screen. */
function segmentDistance(at: ScreenPoint, a: ScreenPoint, b: ScreenPoint): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = dx * dx + dy * dy;
  const t =
    length > 0 ? Math.max(0, Math.min(1, ((at.x - a.x) * dx + (at.y - a.y) * dy) / length)) : 0;
  return Math.hypot(at.x - (a.x + t * dx), at.y - (a.y + t * dy));
}

function modeOf(event: { shift: boolean; ctrl: boolean }): 'replace' | 'add' | 'remove' {
  if (event.ctrl) return 'remove';
  return event.shift ? 'add' : 'replace';
}

export function createNetInteraction(
  editor: NetEditor,
  viewport: Viewport,
  hooks: NetInteractionHooks,
): ViewportInteraction {
  let gesture: Gesture | null = null;
  /** Where the pointer was last seen over the viewport (keys act there). */
  let lastPointer: ScreenPoint | null = null;

  /** Visible control points with their screen positions (front-facing only). */
  const visiblePoints = function* (): Generator<{ control: number; screen: ScreenPoint }> {
    for (let control = 0; control < editor.controlCount; control += 1) {
      const point = editor.limitPoint(control);
      const screen = viewport.worldToScreen(point);
      if (!screen) continue;
      const ray = viewport.screenToRay(screen);
      if (dot(editor.normalAt(control), ray.direction) > FACING_LIMIT) continue;
      yield { control, screen };
    }
  };

  /** The pickable control point under the pointer, and the visible ones around it. */
  const pointsAt = (at: ScreenPoint): { picked: number | null; nearby: number[] } => {
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
  };
  const pickControl = (at: ScreenPoint): number | null => pointsAt(at).picked;

  /** The visible net edge under the pointer, with whether it is open border. */
  const edgeAt = (at: ScreenPoint): { edge: Edge; border: boolean } | null => {
    const edges = editor.edges;
    if (!edges) return null;
    const screens = new Map<number, ScreenPoint | null>();
    const screenOf = (control: number): ScreenPoint | null => {
      if (screens.has(control)) return screens.get(control) ?? null;
      const point = editor.limitPoint(control);
      let screen = viewport.worldToScreen(point);
      if (
        screen &&
        dot(editor.normalAt(control), viewport.screenToRay(screen).direction) > FACING_LIMIT
      )
        screen = null;
      screens.set(control, screen);
      return screen;
    };
    let best: { edge: Edge; border: boolean } | null = null;
    let bestDistance = EDGE_RADIUS_PX;
    for (let index = 0; index < edges.pairs.length / 2; index += 1) {
      const a = edges.pairs[index * 2] ?? 0;
      const b = edges.pairs[index * 2 + 1] ?? 0;
      const sa = screenOf(a);
      const sb = screenOf(b);
      if (!sa || !sb) continue;
      const distance = segmentDistance(at, sa, sb);
      if (distance < bestDistance) {
        bestDistance = distance;
        const border = (edges.border[index] ?? 0) !== 0;
        best = { edge: (border && editor.borderEdge(a, b)) || { a, b }, border };
      }
    }
    return best;
  };

  /** The scan point under the pointer and the scan's outward normal there. */
  const scanAt = (at: ScreenPoint): { point: Vec3; normal: Vec3 } | null => {
    const hit = viewport.pick(at, { kinds: ['scan'] });
    if (!hit || hit.kind !== 'scan') return null;
    const ray = viewport.screenToRay(at);
    const normal = viewport.scanSurface.closest(hit.point, 1)?.normal ?? [
      -ray.direction[0],
      -ray.direction[1],
      -ray.direction[2],
    ];
    return { point: hit.point, normal };
  };

  /** The view plane through a point: drags move in it. */
  const viewPlane = (origin: Vec3): { origin: Vec3; normal: Vec3 } => {
    const at = viewport.worldToScreen(origin);
    const normal = at ? viewport.screenToRay(at).direction : ([0, 0, 1] as Vec3);
    return { origin, normal };
  };

  /** Offset of the grabbed surface point for the pointer at `screen`. */
  const dragOffset = (
    screen: ScreenPoint,
    alongNormal: boolean,
    control: number,
    plane: { origin: Vec3; normal: Vec3 },
  ): Vec3 | null => {
    const ray = viewport.screenToRay(screen);
    if (alongNormal) {
      // Closest point of the normal line through the grabbed point to the pointer ray.
      const normal = editor.normalAt(control);
      const w0 = sub(plane.origin, ray.origin);
      const b = dot(normal, ray.direction);
      const denominator = 1 - b * b;
      if (Math.abs(denominator) < 1e-6) return null;
      const t = (b * dot(ray.direction, w0) - dot(normal, w0)) / denominator;
      return [normal[0] * t, normal[1] * t, normal[2] * t];
    }
    const denominator = dot(plane.normal, ray.direction);
    if (Math.abs(denominator) < 1e-9) return null;
    const s = dot(plane.normal, sub(plane.origin, ray.origin)) / denominator;
    return sub(add(ray.origin, ray.direction, s), plane.origin);
  };

  const boxPoints = (from: ScreenPoint, to: ScreenPoint): number[] => {
    const minX = Math.min(from.x, to.x);
    const maxX = Math.max(from.x, to.x);
    const minY = Math.min(from.y, to.y);
    const maxY = Math.max(from.y, to.y);
    const inside: number[] = [];
    for (const { control, screen } of visiblePoints()) {
      if (screen.x >= minX && screen.x <= maxX && screen.y >= minY && screen.y <= maxY)
        inside.push(control);
    }
    return inside;
  };

  return {
    cursor: 'default',
    onPointerMove: (event) => {
      lastPointer = event.screen;
      if (!gesture) {
        const facing = editor.getState().facing;
        if (facing) {
          editor.previewFacePoint(scanAt(event.screen)?.point ?? null);
          return false;
        }
        if (editor.controlCount === 0) return false;
        const { picked, nearby } = pointsAt(event.screen);
        editor.setHover(picked, nearby);
        editor.setHoverEdge(picked === null ? (edgeAt(event.screen)?.edge ?? null) : null);
        return false;
      }
      if (gesture.kind === 'box') {
        hooks.onBox({ from: gesture.start, to: event.screen });
        return true;
      }
      if (gesture.kind === 'edge') {
        const moved = Math.hypot(
          event.screen.x - gesture.start.x,
          event.screen.y - gesture.start.y,
        );
        if (!gesture.moved && moved < DRAG_THRESHOLD_PX) return true;
        gesture.moved = true;
        const ray = viewport.screenToRay(event.screen);
        const { origin, normal } = gesture.plane;
        const denominator = dot(normal, ray.direction);
        if (Math.abs(denominator) < 1e-9) return true;
        const s = dot(normal, sub(origin, ray.origin)) / denominator;
        const offset = sub(add(ray.origin, ray.direction, s), origin);
        if (gesture.facing) gesture.chain = editor.facingChain(gesture.edge, offset);
        gesture.distance = Math.max(0, dot(offset, gesture.outward));
        editor.previewExtrusion(gesture.chain, gesture.distance);
        return true;
      }
      const distance = Math.hypot(
        event.screen.x - gesture.start.x,
        event.screen.y - gesture.start.y,
      );
      if (!gesture.moved) {
        if (distance < DRAG_THRESHOLD_PX) return true;
        if (gesture.mode === 'replace' && !editor.isSelected(gesture.control))
          editor.choose([gesture.control], 'replace');
        else if (gesture.mode === 'add') editor.choose([gesture.control], 'add');
        if (!editor.beginDrag(gesture.control)) {
          gesture = null;
          return true;
        }
        gesture.moved = true;
      }
      const offset = dragOffset(event.screen, event.alt, gesture.control, gesture.plane);
      if (offset) editor.dragBy(offset, event.alt);
      return true;
    },
    onPointerDown: (event) => {
      if (event.button !== 0) return false;
      if (editor.getState().facing) {
        const hit = scanAt(event.screen);
        if (hit) void editor.addFacePoint(hit.point, hit.normal);
        return true;
      }
      if (editor.controlCount === 0) return false;
      const control = pickControl(event.screen);
      if (control !== null) {
        const origin = editor.limitPoint(control);
        const at = viewport.worldToScreen(origin) ?? event.screen;
        const normal = viewport.screenToRay(at).direction;
        gesture = {
          kind: 'point',
          control,
          start: event.screen,
          mode: modeOf(event),
          moved: false,
          plane: { origin, normal },
        };
        return true;
      }
      const under = edgeAt(event.screen);
      if (under?.border) {
        const facing = event.shift && event.ctrl;
        const chain = editor.extrusionChain(under.edge, event.shift && !facing ? 'side' : 'edge');
        const a = editor.limitPoint(under.edge.a);
        const b = editor.limitPoint(under.edge.b);
        const middle: Vec3 = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
        gesture = {
          kind: 'edge',
          edge: under.edge,
          facing,
          chain,
          start: event.screen,
          moved: false,
          plane: viewPlane(middle),
          outward: editor.outwardOf(under.edge),
          distance: 0,
        };
        editor.previewExtrusion(chain, 0);
        return true;
      }
      if (hooks.selectionModeActive()) return false;
      gesture = { kind: 'box', start: event.screen, mode: modeOf(event) };
      return true;
    },
    onPointerUp: (event) => {
      const done = gesture;
      gesture = null;
      if (!done) return false;
      if (done.kind === 'edge') {
        if (done.moved && done.distance > 0) void editor.extrude(done.chain, done.distance);
        else editor.previewExtrusion(null, 0);
        return true;
      }
      if (done.kind === 'box') {
        hooks.onBox(null);
        const small =
          Math.hypot(event.screen.x - done.start.x, event.screen.y - done.start.y) <
          DRAG_THRESHOLD_PX;
        if (small) {
          if (done.mode === 'replace') editor.choose([], 'replace');
        } else editor.choose(boxPoints(done.start, event.screen), done.mode);
        return true;
      }
      if (done.moved) editor.endDrag(true);
      else if (done.mode === 'add') editor.choose([done.control], 'toggle');
      else editor.choose([done.control], done.mode);
      return true;
    },
    onKeyDown: (event) => {
      const plain = !event.ctrlKey && !event.altKey && !event.metaKey;
      if (editor.getState().facing) {
        if (event.key === 'Escape') {
          editor.setFacing(false);
          return true;
        }
        if (event.key === 'Backspace') return editor.removeFacePoint();
        return false;
      }
      if (gesture?.kind === 'edge' && event.key === 'Escape') {
        editor.previewExtrusion(null, 0);
        gesture = null;
        return true;
      }
      if (plain && (event.key === 's' || event.key === 'S') && !gesture) {
        const at = lastPointer;
        const under = at ? edgeAt(at) : null;
        if (!under) return false;
        void editor.split(under.edge);
        return true;
      }
      if (event.key === 'Escape') {
        if (gesture?.kind === 'point' && gesture.moved) {
          editor.endDrag(false);
          gesture = null;
          return true;
        }
        if (gesture?.kind === 'box') {
          hooks.onBox(null);
          gesture = null;
          return true;
        }
        if (editor.getState().selected > 0) {
          editor.choose([], 'replace');
          return true;
        }
        return false;
      }
      if ((event.key === 'a' || event.key === 'A') && event.ctrlKey && editor.controlCount > 0) {
        editor.chooseAll();
        return true;
      }
      return false;
    },
  };
}
