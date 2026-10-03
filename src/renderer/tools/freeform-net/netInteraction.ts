// Pointer and keys of the freeform-net tool, as in QuickSurface's tutorials:
// - a new face: four clicked corners on the scan, or a rectangle from two clicks (on by
//   itself while the net is empty);
// - points: click to choose (Shift adds, Ctrl removes), drag to move them (they stay on
//   the scan; Alt moves along the surface normal), a rectangle chooses several, a
//   border point dropped onto another one welds them;
// - edges: click to choose, double click for the whole chain, drag to move (back onto
//   the scan); the "D" grip at a hovered border edge, or Alt, duplicates the edge (or
//   the chosen chain) into a new row dropped onto the scan or onto other border points;
// - right click opens the context menu; S splits across the edge under the pointer,
//   Q smooths the chosen chain, Space shows only the surface, Delete removes.
// Empty-space gestures are left to an active selection mode, so triangles can still be
// selected while the tool is open. Every hover sets the status-bar hint.

import type { ScreenPoint, Viewport, ViewportInteraction } from '../../viewport/api';
import type { NetEditor } from './netEditor';
import { type DragPlane, createNetPicking } from './netPicking';
import { setNetHint } from './netSession';
import type { Edge } from './netTopology';

const DRAG_THRESHOLD_PX = 3;
/** Two clicks on the same edge within this time and distance are a double click. */
const DOUBLE_CLICK_MS = 400;
const DOUBLE_CLICK_PX = 6;

export interface BoxRectangle {
  from: ScreenPoint;
  to: ScreenPoint;
}

/** A right click in the viewport: where, and the net edge under it (if any). */
export interface NetMenuRequest {
  at: ScreenPoint;
  edge: Edge | null;
}

export interface NetInteractionHooks {
  /** Draw (or clear) the selection rectangle. */
  onBox(rectangle: BoxRectangle | null): void;
  /** Open the context menu. */
  onMenu(request: NetMenuRequest): void;
  /** A triangle selection mode (brush, lasso, ...) is active. */
  selectionModeActive(): boolean;
}

type Mode = 'replace' | 'add' | 'remove';

type Gesture =
  | {
      kind: 'point';
      control: number;
      start: ScreenPoint;
      mode: Mode;
      moved: boolean;
      plane: DragPlane;
    }
  | { kind: 'box'; start: ScreenPoint; mode: Mode }
  | {
      kind: 'edge';
      edge: Edge;
      border: boolean;
      /** Grabbed at its grip or with Alt: the drag duplicates it into a new row. */
      duplicate: boolean;
      start: ScreenPoint;
      mode: Mode;
      /** What the drag became: new rows, moved points, or nothing yet. */
      drag: 'rows' | 'points' | null;
      plane: DragPlane;
    };

function modeOf(event: { shift: boolean; ctrl: boolean }): Mode {
  if (event.ctrl) return 'remove';
  return event.shift ? 'add' : 'replace';
}

const far = (a: ScreenPoint, b: ScreenPoint, pixels: number) =>
  Math.hypot(a.x - b.x, a.y - b.y) >= pixels;

export function createNetInteraction(
  editor: NetEditor,
  viewport: Viewport,
  hooks: NetInteractionHooks,
): ViewportInteraction {
  const picking = createNetPicking(editor, viewport);
  const build = editor.build;
  let gesture: Gesture | null = null;
  /** Where the pointer was last seen over the viewport (keys act there). */
  let lastPointer: ScreenPoint | null = null;
  let lastEdgeClick: { edge: Edge; at: ScreenPoint; time: number } | null = null;

  const hover = (at: ScreenPoint) => {
    const state = editor.getState();
    if (state.facing) {
      const anchor = build.rectangleAnchor;
      if (anchor) {
        const corners = picking.rectangleOnScan(anchor, at);
        build.previewRectangle(corners?.map((corner) => corner.point) ?? null);
      } else build.previewFacePoint(picking.scanAt(at)?.point ?? null);
      const hint =
        state.facePoints === 0 ? 'start' : state.faceMode === 'rectangle' ? 'corner' : 'face';
      setNetHint(hint, state.facePoints + 1);
      return;
    }
    if (editor.controlCount === 0) {
      setNetHint('empty');
      return;
    }
    // Keep the edge while the pointer goes over to its grip.
    if (build.handleAt(at)) {
      setNetHint('handle');
      return;
    }
    const { picked, nearby } = picking.pointsAt(at);
    const under = picked === null ? picking.edgeAt(at) : null;
    editor.setHover(picked, nearby);
    build.setHoverEdge(under?.edge ?? null);
    setNetHint(picked !== null ? 'point' : under ? (under.border ? 'border' : 'edge') : 'idle');
  };

  const placeCorner = (at: ScreenPoint) => {
    if (build.faceMode === 'quad') {
      const corner = picking.scanAt(at);
      if (corner) void build.addFacePoint(corner);
      return;
    }
    const anchor = build.rectangleAnchor;
    if (!anchor) {
      if (picking.scanAt(at)) build.setRectangleAnchor(at);
      return;
    }
    const corners = picking.rectangleOnScan(anchor, at);
    if (corners) void build.addFace(corners);
  };

  const clickEdge = (edge: Edge, at: ScreenPoint, mode: Mode) => {
    const now = performance.now();
    const previous = lastEdgeClick;
    const double =
      !!previous &&
      now - previous.time < DOUBLE_CLICK_MS &&
      !far(at, previous.at, DOUBLE_CLICK_PX) &&
      previous.edge.a === edge.a &&
      previous.edge.b === edge.b;
    lastEdgeClick = double ? null : { edge, at, time: now };
    if (mode === 'replace') editor.choose([], 'replace');
    if (double) build.chooseEdges(build.chainOf(edge), mode);
    else build.chooseEdges([edge], mode === 'add' ? 'toggle' : mode);
  };

  /** Start moving the points of the grabbed edge (and of the chosen edges with it). */
  const beginEdgePoints = (edge: Edge): boolean => {
    const edges = build.isChosen(edge) ? build.chosenEdges() : [edge];
    editor.choose(
      edges.flatMap(({ a, b }) => [a, b]),
      'replace',
    );
    return editor.pointDrag.begin();
  };

  const moveEdge = (current: Extract<Gesture, { kind: 'edge' }>, at: ScreenPoint) => {
    const delta = { x: at.x - current.start.x, y: at.y - current.start.y };
    if (!current.drag) {
      if (!far(at, current.start, DRAG_THRESHOLD_PX)) return;
      if (current.duplicate && current.border && build.beginRows(current.edge))
        current.drag = 'rows';
      else if (beginEdgePoints(current.edge)) current.drag = 'points';
      else {
        gesture = null;
        return;
      }
    }
    if (current.drag === 'rows') {
      build.dragRows(delta);
      setNetHint('rows');
      return;
    }
    const offset = picking.dragOffset(at, current.plane, null);
    if (offset) editor.pointDrag.move(offset, delta);
  };

  const movePoint = (
    current: Extract<Gesture, { kind: 'point' }>,
    at: ScreenPoint,
    alt: boolean,
  ) => {
    if (!current.moved) {
      if (!far(at, current.start, DRAG_THRESHOLD_PX)) return;
      build.chooseEdges([], 'replace');
      if (!editor.isSelected(current.control))
        editor.choose([current.control], current.mode === 'add' ? 'add' : 'replace');
      if (!editor.pointDrag.begin()) {
        gesture = null;
        return;
      }
      current.moved = true;
    }
    const normal = alt ? editor.normalAt(current.control) : null;
    const offset = picking.dragOffset(at, current.plane, normal);
    const delta = alt ? null : { x: at.x - current.start.x, y: at.y - current.start.y };
    if (offset) editor.pointDrag.move(offset, delta);
    // A single border point dropped onto another one is welded: show where.
    build.previewWeld(editor.getState().selected === 1 ? current.control : null);
  };

  const finish = (done: Gesture, at: ScreenPoint) => {
    if (done.kind === 'edge') {
      if (done.drag === 'rows') void build.endRows(true);
      else if (done.drag === 'points') editor.pointDrag.end(true);
      else clickEdge(done.edge, at, done.mode);
    } else if (done.kind === 'box') {
      hooks.onBox(null);
      if (done.mode === 'replace') build.chooseEdges([], 'replace');
      if (far(at, done.start, DRAG_THRESHOLD_PX))
        editor.choose(picking.pointsInBox(done.start, at), done.mode);
      else if (done.mode === 'replace') editor.choose([], 'replace');
    } else if (done.moved) {
      build.previewWeld(null);
      editor.pointDrag.end(true);
    } else {
      if (done.mode === 'replace') build.chooseEdges([], 'replace');
      editor.choose([done.control], done.mode === 'add' ? 'toggle' : done.mode);
    }
  };

  /** Escape: stop the running gesture, else drop the chosen edges, else the points. */
  const cancel = (): boolean => {
    const current = gesture;
    gesture = null;
    if (current?.kind === 'edge' && current.drag === 'rows') void build.endRows(false);
    else if (current?.kind === 'edge' && current.drag === 'points') editor.pointDrag.end(false);
    else if (current?.kind === 'point' && current.moved) {
      build.previewWeld(null);
      editor.pointDrag.end(false);
    } else if (current?.kind === 'box') hooks.onBox(null);
    else if (editor.getState().chosenEdges > 0) build.chooseEdges([], 'replace');
    else if (editor.getState().selected > 0) editor.choose([], 'replace');
    else return false;
    return true;
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
      else if (gesture.kind === 'edge') moveEdge(gesture, event.screen);
      else movePoint(gesture, event.screen, event.alt);
      return true;
    },
    onPointerDown: (event) => {
      if (event.button !== 0) return false;
      if (editor.getState().facing) {
        if (hooks.selectionModeActive()) return false;
        placeCorner(event.screen);
        hover(event.screen);
        return true;
      }
      if (editor.controlCount === 0) return false;
      const mode = modeOf(event);
      const control = picking.pointsAt(event.screen).picked;
      if (control !== null) {
        const plane = picking.viewPlane(editor.limitPoint(control));
        gesture = { kind: 'point', control, start: event.screen, mode, moved: false, plane };
        return true;
      }
      const grip = build.handleAt(event.screen);
      const under = grip ? { edge: grip, border: true } : picking.edgeAt(event.screen);
      if (under) {
        const [a, b] = [editor.limitPoint(under.edge.a), editor.limitPoint(under.edge.b)];
        const plane = picking.viewPlane([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2]);
        const duplicate = !!grip || event.alt;
        gesture = {
          kind: 'edge',
          ...under,
          duplicate,
          start: event.screen,
          mode,
          drag: null,
          plane,
        };
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
      finish(done, event.screen);
      hover(event.screen);
      return true;
    },
    onContextMenu: (event) => {
      if (gesture || editor.getState().facing) return false;
      hooks.onMenu({ at: event.screen, edge: picking.edgeAt(event.screen)?.edge ?? null });
      return true;
    },
    onKeyDown: (event) => {
      const plain = !event.ctrlKey && !event.altKey && !event.metaKey;
      const key = event.key.toLowerCase();
      if (editor.getState().facing) {
        if (event.key === 'Escape') {
          build.setFacing(false);
          return true;
        }
        return event.key === 'Backspace' ? build.removeFacePoint() : false;
      }
      if (event.key === 'Escape') return cancel();
      if (gesture) return false;
      if (event.key === 'Delete') return build.edits.deleteChosen();
      if (plain && key === ' ') {
        editor.setNetVisible(!editor.getState().netVisible);
        return true;
      }
      if (plain && key === 'q' && editor.getState().selected + editor.getState().chosenEdges > 0) {
        void editor.smoothChosen();
        return true;
      }
      if (plain && key === 's') {
        const under = lastPointer ? picking.edgeAt(lastPointer) : null;
        if (!under) return false;
        void build.edits.split(under.edge);
        return true;
      }
      if (key === 'a' && event.ctrlKey && editor.controlCount > 0) {
        editor.chooseAll();
        return true;
      }
      return false;
    },
  };
}
