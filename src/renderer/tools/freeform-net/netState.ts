// What the freeform-net panel shows of the NetEditor (its subscribed snapshot).

import type { KernelFailure } from '../../kernel/KernelFailure';
import type { DeviationSummary } from './heatmap';

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
  summary: DeviationSummary | null;
  job: { kind: NetJobKind; fraction: number | null; stage: string | null } | null;
  error: KernelFailure | null;
  snap: boolean;
  heatmap: boolean;
  /** Tolerance of the colour scale (mm). */
  tolerance: number;
  canUndo: boolean;
  canRedo: boolean;
  /** A face is being placed by clicks on the scan. */
  facing: boolean;
  /** Corners of that face clicked so far (0..3). */
  facePoints: number;
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
    summary: null,
    job: null,
    error: null,
    snap: true,
    heatmap: true,
    tolerance,
    canUndo: false,
    canRedo: false,
    facing: false,
    facePoints: 0,
    chosenEdges: 0,
  };
}
