import { describe, expect, it } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { visibleReferences } from '../freeform-net/netReferences';
import { initialInputs, inputCount, toggleInput, trimCandidates } from './inputs';

type Snapshot = Pick<DocumentSnapshot, 'document' | 'status'>;

/** Features with their state; a body for every id in `bodies`. */
function snapshot(
  features: { id: string; type: string; params?: unknown; state?: string }[],
  bodies: string[],
): Snapshot {
  return {
    document: {
      features: features.map(({ id, type, params }) => ({
        id,
        type,
        name: null,
        suppressed: false,
        params: params ?? {},
      })),
    },
    status: {
      features: Object.fromEntries(
        features.map(({ id, state }) => [id, { state: state ?? 'ok' }]),
      ),
      bodies: bodies.map((id) => ({ id })),
    },
  } as never;
}

const doc = snapshot(
  [
    { id: 'f1', type: 'fit', params: { kind: 'plane' } },
    { id: 'f2', type: 'freeformNet', state: 'warning' },
    { id: 'f3', type: 'extrude' },
    { id: 'f4', type: 'freeformNet' },
    { id: 'f5', type: 'freeformNet', state: 'warning' },
  ],
  ['f3', 'f4'],
);

describe('trim inputs', () => {
  it('offers open surfaces, planes (origin planes last) and bodies', () => {
    const candidates = trimCandidates(doc, null);
    // f4 is a closed net: a body, not a surface.
    expect(candidates).toEqual({
      surfaces: ['f2', 'f5'],
      planes: ['f1', 'XY', 'YZ', 'XZ'],
      bodies: ['f3', 'f4'],
    });
    // While f4 is edited, only what comes before it counts.
    expect(trimCandidates(doc, 'f4').surfaces).toEqual(['f2']);
  });

  it('starts with the chosen objects, else the newest open surface', () => {
    const candidates = trimCandidates(doc, null);
    expect(initialInputs(candidates, [])).toEqual({ surfaces: ['f5'], planes: [], bodies: [] });
    const chosen = initialInputs(candidates, [
      { kind: 'feature', id: 'f1' },
      { kind: 'body', id: 'f3' },
    ]);
    expect(chosen).toEqual({ surfaces: [], planes: ['f1'], bodies: ['f3'] });
    const toggled = toggleInput(chosen, 'planes', 'XY', candidates.planes);
    expect(toggled.planes).toEqual(['f1', 'XY']);
    expect(inputCount(toggleInput(toggled, 'planes', 'f1', candidates.planes))).toBe(2);
  });
});

describe('push references', () => {
  it('are the shown planes and bodies', () => {
    const hidden = { bodies: ['f4'], owners: [] };
    expect(visibleReferences(doc, hidden, 'both')).toEqual({ planes: ['f1'], bodies: ['f3'] });
    expect(visibleReferences(doc, { bodies: [], owners: ['f1'] }, 'bodies').planes).toEqual([]);
    expect(visibleReferences(doc, hidden, 'scan')).toEqual({ planes: [], bodies: [] });
  });
});
