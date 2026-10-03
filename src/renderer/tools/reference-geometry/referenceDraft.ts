// The reference tool's draft: the kind of definition, its inputs (origin planes and
// axes or feature ids) and its value, plus the rules for picking inputs.

import type {
  ReferenceDefinition,
  ReferenceDefinitionInput,
} from '@shared/protocol/generated/feature-reference';

import { type GeometryKind, ORIGIN_AXES, ORIGIN_PLANES } from '../../features/reference/geometry';

export type DefinitionType = ReferenceDefinition['type'];
export type SlotName = 'plane' | 'axis' | 'a' | 'b';

export const DEFINITION_TYPES: readonly DefinitionType[] = [
  'offsetPlane',
  'planeThroughAxis',
  'midPlane',
  'axisFromPlanes',
];

export interface Slot {
  name: SlotName;
  /** What the input must provide. */
  kind: Extract<GeometryKind, 'plane' | 'axis'>;
}

const SLOTS: Readonly<Record<DefinitionType, readonly Slot[]>> = {
  offsetPlane: [{ name: 'plane', kind: 'plane' }],
  planeThroughAxis: [{ name: 'axis', kind: 'axis' }],
  midPlane: [
    { name: 'a', kind: 'plane' },
    { name: 'b', kind: 'plane' },
  ],
  axisFromPlanes: [
    { name: 'a', kind: 'plane' },
    { name: 'b', kind: 'plane' },
  ],
};

export interface ReferenceDraft {
  type: DefinitionType;
  inputs: Partial<Record<SlotName, string>>;
  distance: number;
  angleDeg: number;
}

export const EMPTY_REFERENCE: ReferenceDraft = {
  type: 'offsetPlane',
  inputs: {},
  distance: 10,
  angleDeg: 0,
};

export function slotsOf(type: DefinitionType): readonly Slot[] {
  return SLOTS[type];
}

/** Origin planes or axes that can fill a slot of this kind. */
export function originInputs(kind: Slot['kind']): string[] {
  return Object.keys(kind === 'plane' ? ORIGIN_PLANES : ORIGIN_AXES);
}

/** A different definition keeps the inputs whose slot still exists with the same kind. */
export function withType(draft: ReferenceDraft, type: DefinitionType): ReferenceDraft {
  const kept: ReferenceDraft['inputs'] = {};
  for (const slot of SLOTS[type]) {
    const previous = SLOTS[draft.type].find((item) => item.name === slot.name);
    const value = draft.inputs[slot.name];
    if (previous?.kind === slot.kind && value) kept[slot.name] = value;
  }
  return { ...draft, type, inputs: kept };
}

export function withInput(draft: ReferenceDraft, slot: SlotName, input: string): ReferenceDraft {
  return { ...draft, inputs: { ...draft.inputs, [slot]: input } };
}

/** The first slot without input, where the next pick goes; null when all are filled. */
export function nextEmptySlot(draft: ReferenceDraft): SlotName | null {
  return SLOTS[draft.type].find((slot) => !draft.inputs[slot.name])?.name ?? null;
}

/** The wire definition, or null while an input is missing. */
export function definitionOf(draft: ReferenceDraft): ReferenceDefinitionInput | null {
  const { plane, axis, a, b } = draft.inputs;
  switch (draft.type) {
    case 'offsetPlane':
      return plane ? { type: 'offsetPlane', plane, distance: draft.distance } : null;
    case 'planeThroughAxis':
      return axis ? { type: 'planeThroughAxis', axis, angleDeg: draft.angleDeg } : null;
    case 'midPlane':
      return a && b ? { type: 'midPlane', a, b } : null;
    case 'axisFromPlanes':
      return a && b ? { type: 'axisFromPlanes', a, b } : null;
  }
}

/** The draft of a stored reference feature (edit mode). */
export function draftOf(definition: ReferenceDefinition): ReferenceDraft {
  switch (definition.type) {
    case 'offsetPlane':
      return {
        ...EMPTY_REFERENCE,
        type: definition.type,
        inputs: { plane: definition.plane },
        distance: definition.distance,
      };
    case 'planeThroughAxis':
      return {
        ...EMPTY_REFERENCE,
        type: definition.type,
        inputs: { axis: definition.axis },
        angleDeg: definition.angleDeg,
      };
    case 'midPlane':
    case 'axisFromPlanes':
      return {
        ...EMPTY_REFERENCE,
        type: definition.type,
        inputs: { a: definition.a, b: definition.b },
      };
  }
}
