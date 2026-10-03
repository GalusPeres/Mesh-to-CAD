import { describe, expect, it } from 'vitest';

import type { RecognizeResult, RecognizedFeature } from '@shared/protocol/generated/recognize';

import { createFormatter } from '../../i18n/format';
import {
  chosenFeatures,
  defaultChecked,
  groupFeatures,
  groupLabels,
  labelText,
  needsBody,
  sizeText,
} from './model';

function feature(overrides: Partial<RecognizedFeature>): RecognizedFeature {
  return {
    plane: 0,
    kind: 'boss',
    shape: 'circle',
    params: { cx: 0, cy: 0, radius: 4 },
    level: 0,
    height: 2,
    top: 'flat',
    rms: 0.01,
    parent: null,
    group: 0,
    label: [0, 0, 2],
    ...overrides,
  };
}

function result(features: RecognizedFeature[]): RecognizeResult {
  return {
    planes: [],
    features,
    outlines: new Float32Array(0),
    outlineOffsets: new Uint32Array(1),
  };
}

const PANEL = result([
  feature({ group: 0 }),
  feature({ group: 0, params: { cx: 15, cy: 0, radius: 4 } }),
  feature({ group: 1, kind: 'pocket', params: { cx: 40, cy: 0, radius: 6 }, height: 3 }),
  feature({ group: 2, kind: 'boss', params: { cx: 40, cy: 0, radius: 2.5 }, parent: 2 }),
  feature({ group: 3, kind: 'pocket', top: 'through', params: { cx: 5, cy: 5, radius: 3 } }),
  feature({ group: 4, kind: 'boss', shape: 'profile', params: { cx: 9, cy: 9 } }),
]);

describe('recognised shapes in the panel', () => {
  it('lists raised shapes, pockets and holes, the free outlines last', () => {
    const groups = groupFeatures(PANEL);
    expect(groups.map((group) => [group.id, group.role, group.indices])).toEqual([
      [0, 'boss', [0, 1]],
      [2, 'boss', [3]],
      [1, 'pocket', [2]],
      [3, 'hole', [4]],
      [4, 'boss', [5]],
    ]);
    expect(groups.find((group) => group.id === 2)?.nested).toBe(true);
    expect(groups.find((group) => group.id === 4)?.buildable).toBe(false);
  });

  it('checks every buildable group and builds their features', () => {
    const groups = groupFeatures(PANEL);
    const checked = defaultChecked(groups);
    expect([...checked].sort()).toEqual([0, 1, 2, 3]);
    expect(chosenFeatures(groups, checked)).toEqual([0, 1, 2, 3, 4]);
    expect(needsBody(groups, checked)).toBe(true);
    expect(needsBody(groups, new Set([0, 2, 4]))).toBe(false);
    // An unbuildable group is never built, even when checked.
    expect(chosenFeatures(groups, new Set([0, 4]))).toEqual([0, 1]);
  });

  it('labels every group once with its count, free profiles not at all', () => {
    const labels = groupLabels(PANEL, createFormatter('de-DE'));
    expect(labels).toEqual(['2× Ø8,0', null, 'Ø12,0', 'Ø5,0', 'Ø6,0', null]);
  });

  it('describes sizes in the user locale', () => {
    const format = createFormatter('de-DE');
    const slot = feature({ shape: 'slot', params: { length: 10.1, width: 6.45 } });
    const ring = feature({
      shape: 'ringSegment',
      params: { inner: 8.7, outer: 13.5, sweep: Math.PI / 2 },
    });
    expect(sizeText(feature({}), format)).toBe('Ø 8,00 mm');
    expect(sizeText(slot, format)).toBe('10,10 × 6,45 mm');
    expect(sizeText(ring, format)).toBe('R 8,70–13,50 mm · 90°');
    expect(labelText(feature({}), format)).toBe('Ø8,0');
    expect(labelText(slot, format)).toBe('10,1×6,5');
  });
});
