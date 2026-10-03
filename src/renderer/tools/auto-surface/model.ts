// Parameters and results of the Auto-Flächen tool (feature type `autoSurface`).

import type { DocOp } from '@shared/protocol/generated/document-ops';
import type { FeatureStatus } from '@shared/protocol/generated/document-results';
import type {
  AutoSurfaceInput,
  SurfaceDetail,
  SurfaceSmoothing,
} from '@shared/protocol/generated/feature-auto-surface';

export const DETAILS: readonly SurfaceDetail[] = ['coarse', 'medium', 'fine'];
export const SMOOTHINGS: readonly SurfaceSmoothing[] = ['low', 'medium', 'high'];
export const DEFAULT_DETAIL: SurfaceDetail = 'medium';
export const DEFAULT_SMOOTHING: SurfaceSmoothing = 'low';

/** Surface the whole scan, or only the selected triangles. */
export type Source = 'scan' | 'selection';

/** Kernel statistics of an `autoSurface` feature (`features/types/auto_surface.py`). */
export interface SurfaceStats {
  patches: number;
  closed: boolean;
  rms: number | null;
  mean: number | null;
  p95: number | null;
  max: number | null;
}

function numberOrNull(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function surfaceStats(status: FeatureStatus | null | undefined): SurfaceStats | null {
  const patches = numberOrNull(status?.stats.patches);
  if (!status || patches === null) return null;
  return {
    patches,
    closed: status.stats.closed === 1,
    rms: numberOrNull(status.stats.deviationRms),
    mean: numberOrNull(status.stats.deviationMean),
    p95: numberOrNull(status.stats.deviationP95),
    max: numberOrNull(status.stats.deviationMax),
  };
}

/** The operation that adds the feature, or changes the edited one. */
export function autoSurfaceOps(editTarget: string | null, input: AutoSurfaceInput): DocOp[] {
  const params: Record<string, unknown> = { ...input };
  return editTarget
    ? [{ type: 'updateFeature', id: editTarget, params }]
    : [{ type: 'addFeature', feature: { type: 'autoSurface', params } }];
}

/** The feature input for the chosen source; null while a selection is too small. */
export function autoSurfaceInput(
  source: Source,
  selection: Uint32Array | null,
  detail: SurfaceDetail,
  smoothing: SurfaceSmoothing,
  minFaces: number,
): AutoSurfaceInput | null {
  if (source === 'scan') return { faces: null, sourceRegion: null, detail, smoothing };
  if (!selection || selection.length < minFaces) return null;
  return { faces: selection, sourceRegion: null, detail, smoothing };
}
