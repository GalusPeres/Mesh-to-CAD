// Pointer and keys of the freeform-net tool, as in QuickSurface:
// - points: click to choose (Shift adds, Ctrl removes), drag to move them (with Alt
//   along the surface normal), a rectangle chooses several;
// - edges: click to choose, double click for the whole chain; dragging a border edge
//   drops a new row of quads onto the scan where the pointer lets go (out of every
//   chosen border edge if it is chosen), dragging an inner edge moves its points;
// - S over an edge inserts a loop across it; while placing a face, clicks on the scan
//   set its corners.
// Empty-space gestures are left to an active selection mode, so triangles can still be
// selected while the tool is open. Every hover sets the status-bar hint.

import type { ScreenPoint, Vec3, Viewport, ViewportInteraction } from '../../viewport/api';
import type { Edge } from './netTopology';
import type { NetEditor } from './netEditor';
import { createNetPicking } from './netPicking';
import { setNetHint } from './netSession';

const DRAG_THRESHOLD_PX = 3;
/** Two clicks on the same edge within this time and distance are a double click. */
const DOUBLE_CLICK_MS = 400;
const DOUBLE_CLICK_PX = 6;

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

type Mode = 'replace' | 'add' | 'remove';
type Plane = { origin: Vec3; normal: Vec3 };

type Gesture =
  | { kind: 'point'; control: number; start: ScreenPoint; mode: Mode; moved: boolean; plane: Plane }
  | { kind: 'box'; start: ScreenPoint; mode: Mode }
  | {
      kind: 'edge';
      edge: Edge;
      border: boolean;
      start: ScreenPoint;
      mode: Mode;
      /** What the drag became: new rows, moved points, or nothing yet. */
      drag: 'rows' | 'points' | null;
      plane: Plane;
    };

const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const middle = (a: Vec3, b: Vec3): Vec3 => [
  (a[0] + b[0]) / 2,
  (a[1] + b[1]) / 2,
  (a[2] + b[2]) / 2,
];

function modeOf(event: { shift: boolean; ctrl: boolean }): Mode {
  if (event.ctrl) return 'remove';
  return event.shift ? 'add' : 'replace';
}

export function createNetInteraction(
  editor: NetEditor,
  viewport: Viewport,
  hooks: NetInteractionHooks,
): ViewportInteraction {
  const picking = createNetPicking(editor, viewport);
  let gesture: Gesture | null = null;
  /** Where the pointer was last seen over the viewport (keys act there). */
  let lastPointer: ScreenPoint | null = null;
  let lastEdgeClick: { edge: Edge; at: ScreenPoint; time: number } | null = null;

  /** The view plane through a point: drags move in it. */
  const viewPlane = (origin: Vec3): Plane => {
    const at = viewport.worldToScreen(origin);
    return { origin, normal: at ? viewport.screenToRay(at).direction : [0, 0, 1] };
  };

  /** Offset of a grabbed surface point for the pointer at `screen`. */
  const dragOffset = (screen: ScreenPoint, plane: Plane, normal: Vec3 | null): Vec3 | null => {
    const ray = viewport.screenToRay(screen);
    const w0: Vec3 = [
      plane.origin[0] - ray.origin[0],
      plane.origin[1] - ray.origin[1],
      plane.origin[2] - ray.origin[2],
    ];
    if (normal) {
      // Closest point of the normal line through the grabbed point to the pointer ray.
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
  };

  const hover = (at: ScreenPoint) => {
    const state = editor.getState();
    if (state.facing) {
      editor.build.previewFacePoint(picking.scanAt(at)?.point ?? null);
      setNetHint('face', state.facePoints + 1);
      return;
    }
    if (editor.controlCount === 0) {
      setNetHint('start');
      return;
    }
    const { picked, nearby } = picking.pointsAt(at);
    const under = picked === null ? picking.edgeAt(at) : null;
    editor.setHover(picked, nearby);
    editor.build.setHoverEdge(under?.edge ?? null);
    setNetHint(picked !== null ? 'point' : under ? (under.border ? 'border' : 'edge') : 'idle');
  };

  /** Start moving the points of the grabbed edge (and of the chosen edges with it). */
  const beginEdgePoints = (edge: Edge): boolean => {
    const edges = editor.build.isChosen(edge) ? editor.build.chosenEdges() : [edge];
    editor.choose(
      edges.flatMap(({ a, b }) => [a, b]),
      'replace',
    );
    return editor.pointDrag.begin();
  };

  const clickEdge = (edge: Edge, at: ScreenPoint, mode: Mode) => {
    const now = performance.now();
    const previous = lastEdgeClick;
    const double =
      !!previous &&
      now - previous.time < DOUBLE_CLICK_MS &&
      Math.hypot(at.x - previous.at.x, at.y - previous.at.y) < DOUBLE_CLICK_PX &&
      previous.edge.a === edge.a &&
      previous.edge.b === edge.b;
    lastEdgeClick = double ? null : { edge, at, time: now };
    if (mode === 'replace') editor.choose([], 'replace');
    if (double) editor.build.chooseEdges(editor.build.chainOf(edge), mode);
    else editor.build.chooseEdges([edge], mode === 'add' ? 'toggle' : mode);
  };

  const moveEdge = (
    current: Extract<Gesture, { kind: 'edge' }>,
    event: { screen: ScreenPoint; alt: boolean },
  ) => {
    const delta = { x: event.screen.x - current.start.x, y: event.screen.y - current.start.y };
    if (!current.drag) {
      if (Math.hypot(delta.x, delta.y) < DRAG_THRESHOLD_PX) return;
      if (current.border && editor.build.beginRows(current.edge)) current.drag = 'rows';
      else if (beginEdgePoints(current.edge)) current.drag = 'points';
      else {
        gesture = null;
        return;
      }
    }
    if (current.drag === 'rows') {
      editor.build.dragRows(delta);
      setNetHint('rows');
      return;
    }
    const normal = event.alt ? editor.normalAt(current.edge.a) : null;
    const offset = dragOffset(event.screen, current.plane, normal);
    if (offset) editor.pointDrag.moveBy(offset, event.alt);
  };

  const movePoint = (
    current: Extract<Gesture, { kind: 'point' }>,
    event: { screen: ScreenPoint; alt: boolean },
  ) => {
    if (!current.moved) {
      const distance = Math.hypot(
        event.screen.x - current.start.x,
        event.screen.y - current.start.y,
      );
      if (distance < DRAG_THRESHOLD_PX) return;
      editor.build.chooseEdges([], 'replace');
      if (!editor.isSelected(current.control))
        editor.choose([current.control], current.mode === 'add' ? 'add' : 'replace');
      if (!editor.pointDrag.begin()) {
        gesture = null;
        return;
      }
      current.moved = true;
    }
    const normal = event.alt ? editor.normalAt(current.control) : null;
    const offset = dragOffset(event.screen, current.plane, normal);
    if (offset) editor.pointDrag.moveBy(offset, event.alt);
  };

  return {
    cursor: 'default',
    onPointerMove: (event) => {
      lastPointer = event.screen;
      if (!gesture) {
        hover(event.screen);
        return false;
      }
      if (gesture.kind === 'box') hooks.onBox({ from: gesture.start, to: event.screen });
      else if (gesture.kind === 'edge') moveEdge(gesture, event);
      else movePoint(gesture, event);
      return true;
    },
    onPointerDown: (event) => {
      if (event.button !== 0) return false;
      if (editor.getState().facing) {
        const hit = picking.scanAt(event.screen);
        if (hit) void editor.build.addFacePoint(hit.point, hit.normal);
        hover(event.screen);
        return true;
      }
      if (editor.controlCount === 0) return false;
      const mode = modeOf(event);
      const control = picking.pointsAt(event.screen).picked;
      if (control !== null) {
        const plane = viewPlane(editor.limitPoint(control));
        gesture = { kind: 'point', control, start: event.screen, mode, moved: false, plane };
        return true;
      }
      const under = picking.edgeAt(event.screen);
      if (under) {
        const { a, b } = under.edge;
        const plane = viewPlane(middle(editor.limitPoint(a), editor.limitPoint(b)));
        gesture = { kind: 'edge', ...under, start: event.screen, mode, drag: null, plane };
        return true;
      }
      if (hooks.selectionModeActive()) return false;
      gesture = { kind: 'box', start: event.screen, mode };
      return true;
    },
    onPointerUp: (event) => {
      const done = gesture;
      gesture = null;
      if (!done) return false;
      setNetHint('idle');
      if (done.kind === 'edge') {
        if (done.drag === 'rows') void editor.build.endRows(true);
        else if (done.drag === 'points') editor.pointDrag.end(true);
        else clickEdge(done.edge, event.screen, done.mode);
        return true;
      }
      if (done.kind === 'box') {
        hooks.onBox(null);
        const small =
          Math.hypot(event.screen.x - done.start.x, event.screen.y - done.start.y) <
          DRAG_THRESHOLD_PX;
        if (done.mode === 'replace') editor.build.chooseEdges([], 'replace');
        if (!small) editor.choose(picking.pointsInBox(done.start, event.screen), done.mode);
        else if (done.mode === 'replace') editor.choose([], 'replace');
        return true;
      }
      if (done.moved) editor.pointDrag.end(true);
      else {
        if (done.mode === 'replace') editor.build.chooseEdges([], 'replace');
        editor.choose([done.control], done.mode === 'add' ? 'toggle' : done.mode);
      }
      return true;
    },
    onKeyDown: (event) => {
      const plain = !event.ctrlKey && !event.altKey && !event.metaKey;
      if (editor.getState().facing) {
        if (event.key === 'Escape') {
          editor.build.setFacing(false);
          return true;
        }
        return event.key === 'Backspace' ? editor.build.removeFacePoint() : false;
      }
      if (event.key === 'Escape') return cancel();
      if (event.key === 'Delete' && !gesture) return editor.build.deleteChosen();
      if (plain && (event.key === 's' || event.key === 'S') && !gesture) {
        const under = lastPointer ? picking.edgeAt(lastPointer) : null;
        if (!under) return false;
        void editor.build.split(under.edge);
        return true;
      }
      if ((event.key === 'a' || event.key === 'A') && event.ctrlKey && editor.controlCount > 0) {
        editor.chooseAll();
        return true;
      }
      return false;
    },
  };

  /** Escape: stop the running gesture, else drop the chosen edges, else the points. */
  function cancel(): boolean {
    const current = gesture;
    gesture = null;
    if (current?.kind === 'edge' && current.drag === 'rows') void editor.build.endRows(false);
    else if (current?.kind === 'edge' && current.drag === 'points') editor.pointDrag.end(false);
    else if (current?.kind === 'point' && current.moved) editor.pointDrag.end(false);
    else if (current?.kind === 'box') hooks.onBox(null);
    else if (editor.getState().chosenEdges > 0) editor.build.chooseEdges([], 'replace');
    else if (editor.getState().selected > 0) editor.choose([], 'replace');
    else return false;
    return true;
  }
}
