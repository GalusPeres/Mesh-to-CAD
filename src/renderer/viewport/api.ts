// The viewport as tools and panels see it. Everything outside viewport/ uses only
// this interface; the implementation (SceneController) can change freely.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { SceneItem } from '@shared/protocol/generated/document-display';

import type { Projection } from '../state/viewStore';
import type { DeviationScheme } from './palette';

export type Vec3 = readonly [number, number, number];

/** CSS pixels relative to the top left corner of the viewport canvas. */
export interface ScreenPoint {
  x: number;
  y: number;
}

export interface Ray {
  origin: Vec3;
  direction: Vec3;
}

export type StandardView = 'front' | 'back' | 'left' | 'right' | 'top' | 'bottom' | 'iso';

export type PickHit =
  | { kind: 'scan'; face: number; point: Vec3 }
  | { kind: 'body'; bodyId: string; face: number; point: Vec3 }
  | { kind: 'edge'; bodyId: string; edge: number; point: Vec3 }
  | { kind: 'item'; key: string; owner: string; point: Vec3 };

/** Objects the project tree hides: bodies by body id, other items by their owner feature. */
export interface HiddenObjects {
  bodies: readonly string[];
  owners: readonly string[];
}

export interface PickOptions {
  kinds?: readonly PickHit['kind'][];
}

/** Pass/fail state per face of a fit or sketch preview (docs/DESIGN.md 6.3). */
export const FACE_STATE = { none: 0, pass: 1, fail: 2, failFar: 3 } as const;

export interface DeviationDisplay {
  tolerance: number;
  range: number;
  scheme: DeviationScheme;
}

export interface ScanView {
  readonly faceCount: number;
  /** Key of the displayed scan (`Scan.key`); selection state is tagged with it. */
  readonly scanKey: string | null;
  /** One byte per face, 1 = selected. */
  setSelection(mask: Uint8Array): void;
  /** Change the selection state of some faces (brush strokes). */
  updateSelection(faces: Uint32Array, selected: boolean): void;
  /** Hover pre-highlight (smart select preview, tree hover). */
  setHover(faces: Uint32Array | null): void;
  /** One byte per face, 1 = hidden; null shows everything. */
  setHidden(mask: Uint8Array | null): void;
  /** Pass/fail colouring of the given faces (a `FACE_STATE` value per face); null clears it. */
  setFaceStates(faces: Uint32Array | null, states?: Uint8Array): void;
  setRegions(labels: Uint16Array | null, colorIndex: Uint8Array | null): void;
  /** Signed distance per scan vertex (NaN = no data); null turns the colour map off. */
  setDeviation(values: Float32Array | null, display?: DeviationDisplay): void;
  /** Scan opacity, e.g. 0.15 while sketching. */
  setOpacity(opacity: number): void;
}

export interface CameraView {
  fitAll(): void;
  fitBox(min: Vec3, max: Vec3): void;
  setStandardView(view: StandardView): void;
  /** Look straight at a plane (sketch mode). */
  lookAlong(origin: Vec3, normal: Vec3, xDirection: Vec3): void;
  setProjection(projection: Projection): void;
  /** Lock orbiting (sketch mode); pan and zoom stay available. */
  setOrbitLocked(locked: boolean): void;
}

export interface HandleEvents {
  /** Called while dragging with the new value (distance, angle in degrees or point). */
  onChange?(value: number | Vec3): void;
  onCommit?(value: number | Vec3): void;
}

export interface ArrowHandleOptions extends HandleEvents {
  origin: Vec3;
  direction: Vec3;
  /** Current distance along the direction. */
  value: number;
  color?: 'axis' | 'neutral';
}

export interface ArcHandleOptions extends HandleEvents {
  center: Vec3;
  axis: Vec3;
  /** Direction of angle 0, perpendicular to the axis. */
  reference: Vec3;
  radius: number;
  /** Current angle in degrees. */
  value: number;
}

export interface PlaneHandleOptions extends HandleEvents {
  origin: Vec3;
  normal: Vec3;
  xDirection: Vec3;
  size: number;
  /** Offset along the normal. */
  value: number;
}

export interface PointHandleOptions extends HandleEvents {
  position: Vec3;
  /** The point moves in this plane. */
  planeNormal: Vec3;
}

export interface Handle {
  dispose(): void;
}

export interface HandleFactory {
  arrow(options: ArrowHandleOptions): Handle;
  arc(options: ArcHandleOptions): Handle;
  plane(options: PlaneHandleOptions): Handle;
  point(options: PointHandleOptions): Handle;
}

export interface ViewportPointerEvent {
  screen: ScreenPoint;
  /** `MouseEvent.button` of the change (0 left, 1 middle, 2 right). */
  button: number;
  buttons: number;
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
}

/**
 * Pointer handling of a selection mode or a panel tool. Handlers return true to
 * consume the event (then no navigation happens and lower interactions do not see it).
 * Interactions added later are asked first.
 */
export interface ViewportInteraction {
  cursor?: string;
  onPointerDown?(event: ViewportPointerEvent): boolean | void;
  onPointerMove?(event: ViewportPointerEvent): boolean | void;
  onPointerUp?(event: ViewportPointerEvent): boolean | void;
  onWheel?(event: ViewportPointerEvent & { deltaY: number }): boolean | void;
  onKeyDown?(event: KeyboardEvent): boolean | void;
  /** A right click without a drag (the camera did not orbit): open a context menu. */
  onContextMenu?(event: ViewportPointerEvent): boolean | void;
}

/** A group of three.js objects owned by a tool; removed from the scene on dispose. */
export interface Overlay {
  add(object: unknown): void;
  clear(): void;
  dispose(): void;
  /**
   * Draw a material's geometry in front of the scan wherever it lies within the
   * tolerance of it, like bodies (viewport/depthBias.ts). `scale` 1 for surfaces,
   * more for lines and points that sit on them.
   */
  applyDepthBias(material: unknown, scale?: number): void;
  /** `applyDepthBias` for a fat-line `LineMaterial` (lines wider than one pixel). */
  applyFatLineDepthBias(material: unknown, scale?: number): void;
}

/** The scan surface point nearest to a point, in part coordinates. */
export interface ScanSurfacePoint {
  point: Vec3;
  /** Outward unit normal of the scan triangle there. */
  normal: Vec3;
  /** Signed distance of the query point: positive outside the material. */
  distance: number;
}

export interface ScanSurfaceQueries {
  /**
   * The scan point nearest to a part-coordinate point within `maxDistance`, or null.
   * Null as well until the scan's search structure exists (after `scanTopology()`).
   */
  closest(point: Vec3, maxDistance: number): ScanSurfacePoint | null;
  /**
   * Signed distances of part-coordinate points (x, y, z triples) to the scan:
   * positive outside the material, NaN beyond `maxDistance`. With `indices` only
   * those points are measured. Returns false (and writes nothing) until the scan's
   * search structure exists.
   */
  distances(
    points: Float32Array,
    out: Float32Array,
    maxDistance: number,
    indices?: Uint32Array,
  ): boolean;
}

export interface ScanTopology {
  /** (F, 3) neighbour face per edge, -1 at open or non-manifold edges. */
  neighbours: Int32Array;
  /** (F, 3) face centroids in part coordinates. */
  centroids: Float32Array;
}

export interface Viewport {
  readonly scan: ScanView;
  readonly camera: CameraView;
  readonly handles: HandleFactory;
  pick(at: ScreenPoint, options?: PickOptions): PickHit | null;
  pickScanFacesInCircle(
    at: ScreenPoint,
    radiusPx: number,
    options: { visibleOnly: boolean },
  ): Uint32Array;
  pickScanFacesInPolygon(
    polygon: Float32Array,
    options: { visibleOnly: boolean },
  ): Promise<Uint32Array>;
  scanTopology(): Promise<ScanTopology>;
  /** Closest points on the scan and distances to it (snapping, live deviation). */
  readonly scanSurface: ScanSurfaceQueries;
  screenToRay(at: ScreenPoint): Ray;
  worldToScreen(point: Vec3): ScreenPoint | null;
  /** Draw the display items of a tool preview (`doc.preview` result); [] removes them. */
  setPreviewItems(owner: string, items: readonly SceneItem[]): void;
  /** Hide the document items of one owner (a feature being edited in place); null shows all. */
  setOwnerHidden(owner: string | null): void;
  /**
   * Leave out hidden bodies and the other document items (sections, planes, sketches)
   * of hidden features, as the project tree hides them. Tool previews stay drawn.
   */
  setHiddenObjects(hidden: HiddenObjects): void;
  /** Hover or selection highlight of an object drawn in the scene. */
  highlight(target: { bodyId: string; edge?: number } | { owner: string } | null): void;
  addInteraction(interaction: ViewportInteraction): () => void;
  createOverlay(): Overlay;
  invalidate(): void;
  capture(options?: { width?: number; height?: number }): Promise<Blob>;
  /** What is drawn right now (diagnostics and end-to-end tests). */
  stats(): { scanFaces: number; items: number };
}

const viewportStore = createStore<{ viewport: Viewport | null }>(() => ({ viewport: null }));

/** The mounted viewport, or null before the canvas exists. */
export function getViewport(): Viewport | null {
  return viewportStore.getState().viewport;
}

export function useViewport(): Viewport | null {
  return useStore(viewportStore, (state) => state.viewport);
}

/** Called by the viewport implementation when it mounts and unmounts. */
export function registerViewport(viewport: Viewport | null): void {
  viewportStore.setState({ viewport });
}
