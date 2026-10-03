// What the freeform-net panel shows of the NetEditor (its subscribed snapshot).

import type { KernelFailure } from '../../kernel/KernelFailure';
import type { DeviationSummary } from './heatmap';
import type { FaceMode } from './netFacePlacement';

export type NetJobKind = 'generate' | 'fit' | 'smooth' | 'map' | 'load';

export interface NetEditorState {
  hasNet: boolean;
  quads: number;
  /** CAD faces the net becomes (rectangles of its patch layout). */
  faces: number;
  controlPoints: number;
  irregular: number;
  closed: boolean;
  selected: number;
  /** Pinned points (dragging, snapping and smoothing leave them where they are). */
  pinned: number;
  /** Chosen points that are pinned. */
  chosenPinned: number;
  summary: DeviationSummary | null;
  job: { kind: NetJobKind; fraction: number | null; stage: string | null } | null;
  error: KernelFailure | null;
  snap: boolean;
  /** A drag holds the limit points next to the dragged ones ("Don't move neighbours"). */
  keepNeighbours: boolean;
  /** Share of the pointer's movement dragged points follow (drag strength). */
  strength: number;
  heatmap: boolean;
  /** Tolerance of the colour scale (mm). */
  tolerance: number;
  canUndo: boolean;
  canRedo: boolean;
  /** A face is being placed by clicks on the scan. */
  facing: boolean;
  /** Four clicked corners, or a rectangle from two. */
  faceMode: FaceMode;
  /** Corners of that face clicked so far (0..3). */
  facePoints: number;
  /** The net's points and lines are shown (Space shows only the surface). */
  netVisible: boolean;
  /** Chosen net edges (a drag of a chosen border edge grows rows on all of them). */
  chosenEdges: number;
}

export function initialNetState(tolerance: number): NetEditorState {
  return {
    hasNet: false,
    quads: 0,
    faces: 0,
    controlPoints: 0,
    irregular: 0,
    closed: false,
    selected: 0,
    pinned: 0,
    chosenPinned: 0,
    summary: null,
    job: null,
    error: null,
    snap: true,
    keepNeighbours: false,
    strength: 1,
    heatmap: true,
    tolerance,
    canUndo: false,
    canRedo: false,
    facing: false,
    faceMode: 'quad',
    facePoints: 0,
    netVisible: true,
    chosenEdges: 0,
  };
}
