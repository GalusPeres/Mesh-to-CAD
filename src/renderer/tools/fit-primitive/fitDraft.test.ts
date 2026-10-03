import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';

import type { AppliedSnap } from '@shared/protocol/generated/fitting-intent';
import type { Primitive } from '@shared/protocol/generated/fitting-primitives';

import { createFormatter } from '../../i18n/format';
import {
  EMPTY_DRAFT,
  draftOf,
  featureInput,
  fixValue,
  isFixed,
  kindOptions,
  parallelAxis,
  perpendicularAxis,
  previewParams,
  primitiveValue,
  rejectSnap,
  releaseValue,
  snapItems,
  selectionAfterFit,
  withKind,
  withRelation,
} from './fitDraft';

const format = createFormatter('de-DE');
const t = ((key: string, options?: Record<string, unknown>) =>
  `${key}${options ? JSON.stringify(options) : ''}`) as unknown as TFunction;

describe('computed and fixed values', () => {
  it('fixing a value of an automatic fit switches to the shown type', () => {
    const draft = fixValue(EMPTY_DRAFT, 'cylinder', 'radius', 8);
    expect(draft.kind).toBe('cylinder');
    expect(draft.fixed).toEqual({ radius: 8 });
    expect(isFixed(draft, 'radius')).toBe(true);
  });

  it('releasing a value lets the fit compute it again', () => {
    const draft = releaseValue(fixValue(EMPTY_DRAFT, 'cylinder', 'radius', 8), 'radius');
    expect(draft.fixed).toEqual({});
    expect(draft.kind).toBe('cylinder');
    expect(isFixed(draft, 'radius')).toBe(false);
  });

  it('a new type keeps only the values that still apply', () => {
    let draft = fixValue(EMPTY_DRAFT, 'cylinder', 'radius', 8);
    draft = fixValue(draft, 'cylinder', 'point', [1, 2, 3]);
    expect(withKind(draft, 'sphere').fixed).toEqual({ radius: 8, point: [1, 2, 3] });
    expect(withKind(draft, 'plane').fixed).toEqual({});
    expect(withKind(draft, 'auto').fixed).toEqual({});
  });

  it('a fixed direction and a relation exclude each other', () => {
    const related = withRelation(EMPTY_DRAFT, 'cylinder', { type: 'parallel', to: 'Z' });
    expect(related.kind).toBe('cylinder');
    const fixed = fixValue(related, 'cylinder', 'direction', [0, 0, 1]);
    expect(fixed.relation).toBeNull();
    const again = withRelation(fixed, 'cylinder', { type: 'perpendicular', to: 'X' });
    expect(again.fixed.direction).toBeUndefined();
    expect(withKind(again, 'sphere').relation).toBeNull();
  });

  it('reads computed values from the fitted primitive', () => {
    const plane: Primitive = { type: 'plane', origin: [3, 4, 12], normal: [0, 0, 1] };
    expect(primitiveValue(plane, 'offset')).toBe(12);
    const cone: Primitive = {
      type: 'cone',
      apex: [0, 0, 0],
      axis: [0, 0, 1],
      halfAngle: Math.PI / 4,
    };
    expect(primitiveValue(cone, 'halfAngleDeg')).toBeCloseTo(45, 12);
    expect(primitiveValue(cone, 'radius')).toBeNull();
  });
});

describe('kernel parameters', () => {
  it('sends the draft as preview parameters', () => {
    const faces = Uint32Array.from([1, 2, 3]);
    const draft = rejectSnap(fixValue(EMPTY_DRAFT, 'cylinder', 'radius', 8), 'direction');
    expect(previewParams(draft, faces, 'scan:1')).toEqual({
      faces,
      scanKey: 'scan:1',
      kind: 'cylinder',
      robust: false,
      fixed: { radius: 8 },
      relation: null,
      snap: true,
      rejectedSnaps: ['direction'],
    });
  });

  it('stores the type the automatic choice found', () => {
    const input = featureInput(EMPTY_DRAFT, Uint32Array.from([4]), 'cone', 'r2');
    expect(input.kind).toBe('cone');
    expect(input.sourceRegion).toBe('r2');
  });

  it('reads the draft of a stored feature', () => {
    const draft = draftOf({
      faces: 'blob:1' as never,
      sourceRegion: null,
      kind: 'torus',
      robust: true,
      fixed: {
        direction: null,
        point: null,
        radius: null,
        halfAngleDeg: null,
        majorRadius: 18,
        minorRadius: null,
        offset: null,
      },
      relation: { type: 'parallel', to: 'f3' },
      snap: false,
      rejectedSnaps: ['minorRadius'],
    });
    expect(draft).toEqual({
      kind: 'torus',
      robust: true,
      snap: false,
      fixed: { majorRadius: 18 },
      relation: { type: 'parallel', to: 'f3' },
      rejectedSnaps: ['minorRadius'],
    });
  });

  it('does not reject a snap twice', () => {
    const once = rejectSnap(EMPTY_DRAFT, 'radius');
    expect(rejectSnap(once, 'radius')).toBe(once);
  });
});

describe('type selector', () => {
  it('lists Automatisch, then tried types by RMS, then the others in order', () => {
    const options = kindOptions([
      { kind: 'plane', rms: 1.2 },
      { kind: 'cylinder', rms: 0.021 },
      { kind: 'sphere', rms: 0.4 },
    ]);
    expect(options.map((option) => option.value)).toEqual([
      'auto',
      'cylinder',
      'sphere',
      'plane',
      'cone',
      'torus',
    ]);
    expect(options[1]?.rms).toBe(0.021);
    expect(options[4]?.rms).toBeNull();
  });
});

describe('snap list', () => {
  const snaps: AppliedSnap[] = [
    {
      id: 'direction',
      kind: 'direction',
      value: 0,
      measured: 0.047,
      uncertainty: 0.012,
      target: 'Z',
    },
    { id: 'radius', kind: 'length', value: 8, measured: 7.987, uncertainty: 0.012, target: null },
    { id: 'halfAngle', kind: 'angle', value: 45, measured: 44.98, uncertainty: 0.02, target: null },
  ];

  it('maps each snap to its text and measurement', () => {
    const items = snapItems(snaps, 'cylinder', format, t);
    expect(items.map((item) => item.id)).toEqual(['direction', 'radius', 'halfAngle']);
    expect(items[0]?.text).toBe('tools:fitPrimitive.snaps.axis.parallel{"axis":"Z"}');
    expect(items[0]?.measured).toBe('0,05 ± 0,01°');
    expect(items[1]?.text).toBe('tools:fitPrimitive.snaps.radius{"value":"8,000 mm"}');
    expect(items[1]?.measured).toBe('7,987 ± 0,012');
    expect(items[2]?.text).toBe('tools:fitPrimitive.snaps.halfAngle{"value":"45,00°"}');
  });

  it('names the normal of planes', () => {
    const [item] = snapItems([{ ...snaps[0]!, value: 90, target: 'X' }], 'plane', format, t);
    expect(item?.text).toBe('tools:fitPrimitive.snaps.normal.perpendicular{"axis":"X"}');
  });
});

describe('directions and selection', () => {
  it('recognises exact axis relations only', () => {
    expect(parallelAxis([0, 0, -1])).toBe('Z');
    expect(parallelAxis([0, 0.0001, Math.sqrt(1 - 1e-8)])).toBeNull();
    expect(perpendicularAxis([0, 0.6, 0.8])).toBe('X');
    expect(perpendicularAxis([0, 0, 1])).toBeNull();
  });

  it('clears the used triangles from the selection unless the setting keeps them', () => {
    const selected = Uint32Array.from([1, 2, 3, 7, 9, 12]);
    const faces = Uint32Array.from([2, 3, 7, 9]);
    const used = Uint8Array.from([1, 0, 1, 1]);
    expect([...(selectionAfterFit(selected, faces, used, true) ?? [])]).toEqual([1, 3, 12]);
    expect(selectionAfterFit(selected, faces, used, false)).toBeNull();
  });
});
