import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { MeasureItem } from '@shared/protocol/generated/inspection';

import { itemFromObject, itemFromPick, itemKey, measureOptions, withPicked } from './measureItems';

const t = ((key: string, options?: Record<string, unknown>) =>
  options ? `${key} ${JSON.stringify(options)}` : key) as unknown as TFunction;

function snapshot(): DocumentSnapshot {
  const params: Record<string, unknown> = {
    fit: { kind: 'plane' },
    sketch: {},
    reference: { definition: { type: 'offsetPlane' } },
  };
  const feature = (id: string, type: string) => ({
    id,
    type,
    name: null,
    suppressed: false,
    params: params[type],
  });
  return {
    revision: 3,
    cause: 'commit',
    label: 'test',
    document: {
      features: [
        feature('f1', 'fit'),
        feature('f2', 'sketch'),
        feature('f3', 'reference'),
        feature('f4', 'fit'),
      ],
    },
    status: {
      features: {
        f1: { state: 'ok', issues: [], error: null, stats: {} },
        f2: { state: 'ok', issues: [], error: null, stats: {} },
        f3: { state: 'warning', issues: [], error: null, stats: {} },
        f4: { state: 'error', issues: [], error: null, stats: {} },
      },
      bodies: [],
    },
  } as unknown as DocumentSnapshot;
}

const face = (faceIndex: number): MeasureItem => ({
  type: 'bodyFace',
  body: 'f9',
  face: faceIndex,
});

describe('measure items', () => {
  it('offers evaluated fits and reference geometry, then the origin items', () => {
    const keys = measureOptions(snapshot(), t).map((option) => option.key);
    expect(keys).toEqual([
      'feature:f1',
      'feature:f3',
      'origin:XY',
      'origin:YZ',
      'origin:XZ',
      'origin:X',
      'origin:Y',
      'origin:Z',
    ]);
  });

  it('turns viewport picks and tree selections into items', () => {
    const current = snapshot();
    expect(
      itemFromPick({ kind: 'body', bodyId: 'f9', face: 4, point: [0, 0, 0] }, current),
    ).toEqual(face(4));
    expect(
      itemFromPick({ kind: 'item', key: 'k', owner: 'f1', point: [0, 0, 0] }, current),
    ).toEqual({ type: 'feature', feature: 'f1' });
    expect(
      itemFromPick({ kind: 'item', key: 'k', owner: 'f2', point: [0, 0, 0] }, current),
    ).toBeNull();
    expect(itemFromPick({ kind: 'scan', face: 1, point: [0, 0, 0] }, current)).toBeNull();
    expect(itemFromObject({ kind: 'feature', id: 'f3' }, current)).toEqual({
      type: 'feature',
      feature: 'f3',
    });
    expect(itemFromObject({ kind: 'feature', id: 'f4' }, current)).toBeNull();
    expect(itemFromObject({ kind: 'body', id: 'f9' }, current)).toBeNull();
  });

  it('fills the first slot, then the second, then starts a new pair', () => {
    let slots = withPicked([null, null], face(1));
    slots = withPicked(slots, face(1));
    expect(slots.map((item) => item && itemKey(item))).toEqual(['face:f9:1', null]);
    slots = withPicked(slots, face(2));
    expect(slots.map((item) => item && itemKey(item))).toEqual(['face:f9:1', 'face:f9:2']);
    slots = withPicked(slots, face(3));
    expect(slots.map((item) => item && itemKey(item))).toEqual(['face:f9:3', null]);
  });
});
