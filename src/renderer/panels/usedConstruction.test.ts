import { describe, expect, it } from 'vitest';

import type { Feature } from '@shared/protocol/generated/document-model';

import { EMPTY_HIDDEN } from './objectVisibility';
import { afterUse, usedFeatures } from './usedConstruction';

const feature = (id: string, type: string, params: Record<string, unknown>): Feature =>
  ({ id, type, name: null, suppressed: false, params }) as Feature;

const history = (features: Feature[]) => ({ document: { features } }) as never;

const plane = feature('f1', 'fit', { kind: 'plane', faces: 'blob:aa' });
const sketch = feature('f2', 'sketch', {
  section: { type: 'planar', plane: { type: 'feature', feature: 'f1' } },
});
const extrude = feature('f3', 'extrude', { sketch: 'f2', targetBody: null });
const button = feature('f4', 'extrude', { sketch: 'f9', targetBody: 'f3' });

describe('used construction', () => {
  it('finds the features later ones read: a plane, a sketch, a changed body', () => {
    expect(usedFeatures(history([plane, sketch, extrude, button]))).toEqual(
      new Set(['f1', 'f2', 'f3']),
    );
    expect(usedFeatures(history([plane, sketch]))).toEqual(new Set(['f1']));
  });

  it('hides used features once, keeps them shown when the user shows them again', () => {
    const hiddenByUse = new Set<string>();
    const first = afterUse(EMPTY_HIDDEN, new Set(['f1', 'f2']), hiddenByUse);
    expect(first).toEqual({ bodies: [], owners: ['f1', 'f2'] });

    const shownAgain = { ...first, owners: ['f2'] };
    expect(afterUse(shownAgain, new Set(['f1', 'f2', 'f3']), hiddenByUse)).toEqual({
      bodies: [],
      owners: ['f2', 'f3'],
    });
  });

  it('shows a feature again when its use is undone, and changes nothing otherwise', () => {
    const hiddenByUse = new Set<string>();
    const hidden = afterUse(EMPTY_HIDDEN, new Set(['f1', 'f2']), hiddenByUse);
    expect(afterUse(hidden, new Set(['f1', 'f2']), hiddenByUse)).toBe(hidden);
    expect(afterUse(hidden, new Set(['f1']), hiddenByUse)).toEqual({
      bodies: [],
      owners: ['f1'],
    });
  });
});
