import { describe, expect, it } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import {
  availableBodies,
  defaultTarget,
  isAxis,
  isBodyFit,
  isPlane,
  isPositiveLength,
  isSketch,
  previewResultKey,
  storedParams,
  targetProblem,
  toolsProblem,
  usableFeatures,
} from './model';

type Snapshot = Pick<DocumentSnapshot, 'document' | 'status'>;

function feature(id: string, type: string, params: unknown = {}) {
  return { id, type, name: null, suppressed: false, params };
}

function body(id: string) {
  return {
    id,
    owner: id,
    valid: true,
    solids: 1,
    volume: 1,
    area: 1,
    maxTolerance: 0,
    faceTags: [],
  };
}

const snapshot = {
  document: {
    features: [
      feature('f1', 'sketch'),
      feature('f2', 'extrude', { sketch: 'f1' }),
      feature('f3', 'fit', { kind: 'plane' }),
      feature('f4', 'fit', { kind: 'cylinder' }),
      feature('f5', 'reference', { definition: { type: 'axisFromPlanes' } }),
      feature('f6', 'reference', { definition: { type: 'offsetPlane' } }),
      feature('f7', 'primitiveBody', { fit: 'f4' }),
      feature('f8', 'sketch'),
    ],
  },
  status: {
    features: {
      f1: { state: 'ok' },
      f2: { state: 'ok' },
      f3: { state: 'warning' },
      f4: { state: 'ok' },
      f5: { state: 'ok' },
      f6: { state: 'error' },
      f7: { state: 'ok' },
      f8: { state: 'ok' },
    },
    bodies: [body('f2'), body('f7')],
  },
} as unknown as Snapshot;

describe('bodies a solid tool may use', () => {
  it('numbers bodies like the tree and keeps only earlier ones while editing', () => {
    expect(availableBodies(snapshot, null)).toEqual([
      { id: 'f2', number: 1 },
      { id: 'f7', number: 2 },
    ]);
    expect(availableBodies(snapshot, 'f7')).toEqual([{ id: 'f2', number: 1 }]);
    expect(availableBodies(snapshot, 'f2')).toEqual([]);
  });

  it('proposes the most recent body as target', () => {
    expect(defaultTarget(availableBodies(snapshot, null))).toBe('f7');
    expect(defaultTarget([])).toBeNull();
  });
});

describe('operation and target body rule', () => {
  const bodies = availableBodies(snapshot, null);

  it('needs no target for a new body', () => {
    expect(targetProblem('newBody', null, bodies)).toBeNull();
  });

  it('needs an existing target for add, cut and intersect', () => {
    for (const operation of ['add', 'cut', 'intersect'] as const) {
      expect(targetProblem(operation, null, bodies)).toBe('targetMissing');
      expect(targetProblem(operation, 'f9', bodies)).toBe('targetUnknown');
      expect(targetProblem(operation, 'f2', bodies)).toBeNull();
    }
  });

  it('checks combine inputs', () => {
    expect(toolsProblem(null, ['f2'])).toBe('targetMissing');
    expect(toolsProblem('f2', [])).toBe('toolsMissing');
    expect(toolsProblem('f2', ['f2', 'f7'])).toBe('targetIsTool');
    expect(toolsProblem('f2', ['f7'])).toBeNull();
  });
});

describe('feature choices', () => {
  it('offers usable features of the right kind before the edited one', () => {
    expect(usableFeatures(snapshot, isSketch, null)).toEqual(['f1', 'f8']);
    expect(usableFeatures(snapshot, isSketch, 'f7')).toEqual(['f1']);
    // f6 is a plane but failed.
    expect(usableFeatures(snapshot, isPlane, null)).toEqual(['f3']);
    expect(usableFeatures(snapshot, isAxis, null)).toEqual(['f4', 'f5']);
    expect(usableFeatures(snapshot, isBodyFit, null)).toEqual(['f4']);
  });

  it('reads stored parameters only for the expected type', () => {
    const full = snapshot as DocumentSnapshot;
    expect(storedParams(full, 'f2', 'extrude')).toEqual({ sketch: 'f1' });
    expect(storedParams(full, 'f2', 'revolve')).toBeNull();
    expect(storedParams(full, null, 'extrude')).toBeNull();
  });
});

describe('lengths', () => {
  it('accepts finite lengths from 1 µm', () => {
    expect(isPositiveLength(12)).toBe(true);
    expect(isPositiveLength(0.001)).toBe(true);
    expect(isPositiveLength(0)).toBe(false);
    expect(isPositiveLength(Number.NaN)).toBe(false);
    expect(isPositiveLength(null)).toBe(false);
  });
});

describe('previewResultKey', () => {
  const body = (key: string, owner = 'f3') => ({ key, owner });

  it('prefers the result key doc.preview returns', () => {
    expect(previewResultKey({ featureId: 'f3', items: [], resultKey: 'r:abc' })).toBe('r:abc');
  });

  it('reads the key of the previewed feature from its body and source items', () => {
    const items = [
      body('body:r:0f1e:f1:t0.02-0.2:faces', 'f1'),
      body('body:r:9f3e:f3:t0.02-0.2:faces'),
      body('src:r:9f3e:0'),
    ];
    expect(previewResultKey({ featureId: 'f3', items })).toBe('r:9f3e');
    expect(previewResultKey({ featureId: 'f3', items: [body('src:r:77aa:1')] })).toBe('r:77aa');
  });

  it('gives null without a feature or matching item', () => {
    expect(previewResultKey({ featureId: null, items: [body('src:r:9f3e:0')] })).toBeNull();
    expect(previewResultKey({ featureId: 'f3', items: [body('scan:1')] })).toBeNull();
  });
});
