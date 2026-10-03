import { describe, expect, it } from 'vitest';

import type { FeatureStatus } from '@shared/protocol/generated/document-results';

import { autoSurfaceInput, autoSurfaceOps, surfaceStats } from './model';

describe('auto surface model', () => {
  it('surfaces the whole scan or a large enough selection', () => {
    expect(autoSurfaceInput('scan', null, 'fine', 'high', 200)).toEqual({
      faces: null,
      sourceRegion: null,
      detail: 'fine',
      smoothing: 'high',
    });
    expect(autoSurfaceInput('selection', new Uint32Array(10), 'coarse', 'low', 200)).toBeNull();
    const faces = Uint32Array.from({ length: 300 }, (_, index) => index);
    expect(autoSurfaceInput('selection', faces, 'coarse', 'low', 200)?.faces).toBe(faces);
  });

  it('adds a feature or updates the edited one', () => {
    const input = autoSurfaceInput('scan', null, 'medium', 'low', 200);
    if (!input) throw new Error('input expected');
    expect(autoSurfaceOps(null, input)).toEqual([
      { type: 'addFeature', feature: { type: 'autoSurface', params: input } },
    ]);
    expect(autoSurfaceOps('f3', input)).toEqual([
      { type: 'updateFeature', id: 'f3', params: input },
    ]);
  });

  it('reads the kernel statistics', () => {
    const status: FeatureStatus = {
      state: 'ok',
      issues: [],
      error: null,
      stats: {
        patches: 3000,
        closed: 1,
        deviationRms: 0.28,
        deviationMean: 0.2,
        deviationP95: 0.6,
        deviationMax: 4.3,
      },
    };
    expect(surfaceStats(status)).toEqual({
      patches: 3000,
      closed: true,
      rms: 0.28,
      mean: 0.2,
      p95: 0.6,
      max: 4.3,
    });
    expect(surfaceStats({ ...status, stats: {} })).toBeNull();
    expect(surfaceStats(null)).toBeNull();
  });
});
