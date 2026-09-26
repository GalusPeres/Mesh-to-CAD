import { describe, expect, it } from 'vitest';

import type { Document, Feature, Region } from '@shared/protocol/generated/document-model';
import type { BlobRef, JsonValue } from '@shared/protocol/wireTypes';

import {
  EMPTY_SLOTS,
  assignInput,
  inputFromObject,
  isComplete,
  previewSlot,
  slotProblems,
  slotsFromObjects,
  slotsFromParams,
  type Slots,
} from './slots';

function fit(id: string, kind: string, suppressed = false): Feature {
  return { id, type: 'fit', name: null, suppressed, params: { kind, faces: 'blob:1' } };
}

function reference(id: string, type: string): Feature {
  const definition: JsonValue = { type };
  return { id, type: 'reference', name: null, suppressed: false, params: { definition } };
}

function region(id: string, kind: Region['kind']): Region {
  return { id, label: 1, name: null, kind, rms: 0.02, faceCount: 900, area: 100, colorIndex: 1 };
}

const document: Pick<Document, 'features' | 'regions'> = {
  features: [
    fit('f1', 'plane'),
    fit('f2', 'cylinder'),
    fit('f3', 'sphere'),
    reference('f4', 'midPlane'),
    { id: 'f5', type: 'extrude', name: null, suppressed: false, params: {} },
    fit('f6', 'plane', true),
  ],
  regions: { labels: null, items: [region('r1', 'plane'), region('r2', 'freeform')] },
};

const selection = (count: number, scanKey = 'scan:a') => ({
  type: 'selection' as const,
  faces: Uint32Array.from({ length: count }, (_, index) => index),
  scanKey,
});

describe('alignment input slots', () => {
  it('needs a primary and a secondary input; the tertiary is optional', () => {
    expect(slotProblems(EMPTY_SLOTS, document, 'scan:a')).toEqual({
      primary: 'missing',
      secondary: 'missing',
    });
    const slots: Slots = {
      primary: { type: 'feature', feature: 'f1' },
      secondary: { type: 'region', region: 'r1' },
      tertiary: null,
    };
    const problems = slotProblems(slots, document, 'scan:a');
    expect(problems).toEqual({});
    expect(isComplete(problems)).toBe(true);
  });

  it('rejects inputs that give no plane, axis or point', () => {
    const slots: Slots = {
      primary: { type: 'feature', feature: 'f3' },
      secondary: { type: 'feature', feature: 'f5' },
      tertiary: { type: 'region', region: 'r2' },
    };
    expect(slotProblems(slots, document, 'scan:a')).toEqual({
      primary: 'pointAsPrimary',
      secondary: 'unsupported',
      tertiary: 'unsupported',
    });
  });

  it('reports missing, suppressed and duplicated inputs', () => {
    const slots: Slots = {
      primary: { type: 'feature', feature: 'f1' },
      secondary: { type: 'feature', feature: 'f1' },
      tertiary: { type: 'feature', feature: 'f6' },
    };
    expect(slotProblems(slots, document, 'scan:a')).toEqual({
      secondary: 'duplicate',
      tertiary: 'unknown',
    });
    const gone: Slots = { ...slots, secondary: { type: 'region', region: 'r9' }, tertiary: null };
    expect(slotProblems(gone, document, 'scan:a')).toEqual({ secondary: 'unknown' });
  });

  it('checks the size and the scan of a selection', () => {
    const slots: Slots = {
      primary: { type: 'feature', feature: 'f2' },
      secondary: selection(50),
      tertiary: selection(500, 'scan:old'),
    };
    expect(slotProblems(slots, document, 'scan:a')).toEqual({
      secondary: 'tooFewFaces',
      tertiary: 'staleSelection',
    });
  });

  it('moves on to the next empty slot after an input is placed', () => {
    let state = assignInput(EMPTY_SLOTS, 'primary', { type: 'feature', feature: 'f1' });
    expect(state.next).toBe('secondary');
    state = assignInput(state.slots, 'secondary', { type: 'feature', feature: 'f2' });
    expect(state.next).toBe('tertiary');
    state = assignInput(state.slots, 'tertiary', { type: 'feature', feature: 'f4' });
    expect(state.next).toBe('tertiary');
    const cleared = assignInput(state.slots, 'primary', null);
    expect(cleared.slots.primary).toBeNull();
    expect(cleared.next).toBe('primary');
  });

  it('accepts fits, reference geometry and typed regions picked in the tree', () => {
    expect(inputFromObject({ kind: 'feature', id: 'f2' }, document)).toEqual({
      type: 'feature',
      feature: 'f2',
    });
    expect(inputFromObject({ kind: 'feature', id: 'f4' }, document)).not.toBeNull();
    expect(inputFromObject({ kind: 'feature', id: 'f5' }, document)).toBeNull();
    expect(inputFromObject({ kind: 'region', id: 'r2' }, document)).toBeNull();
    expect(inputFromObject({ kind: 'body', id: 'f5' }, document)).toBeNull();
  });

  it('fills the slots in order from objects selected before the tool opened', () => {
    const slots = slotsFromObjects(
      [
        { kind: 'body', id: 'f5' },
        { kind: 'feature', id: 'f1' },
        { kind: 'region', id: 'r1' },
        { kind: 'feature', id: 'f2' },
        { kind: 'feature', id: 'f4' },
      ],
      document,
    );
    expect(slots).toEqual({
      primary: { type: 'feature', feature: 'f1' },
      secondary: { type: 'region', region: 'r1' },
      tertiary: { type: 'feature', feature: 'f2' },
    });
  });

  it('round-trips stored parameters and sends selections as triangles', () => {
    const faces = 'blob:abc' as BlobRef;
    const stored: JsonValue = {
      primary: { type: 'feature', feature: 'f1' },
      secondary: { type: 'faces', faces },
      tertiary: null,
    };
    const slots = slotsFromParams(stored);
    expect(slots).toEqual({
      primary: { type: 'feature', feature: 'f1' },
      secondary: { type: 'faces', faces },
      tertiary: null,
    });
    expect(slotsFromParams(null)).toEqual(EMPTY_SLOTS);
    const sent = previewSlot(selection(300));
    expect(sent?.type).toBe('selection');
    expect(sent && 'faces' in sent && sent.faces).toBeInstanceOf(Uint32Array);
    expect(sent).not.toHaveProperty('scanKey');
  });
});
