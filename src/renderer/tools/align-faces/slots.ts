// The three inputs of "An Flächen ausrichten" (3-2-1): what each slot holds, which
// inputs qualify, and when the draft may be previewed. The kernel validates the
// geometry (parallel inputs, a frame without a point); this module checks what can
// be known before asking it.

import type { AlignmentSlot } from '@shared/protocol/generated/alignment';
import type { InputRole } from '@shared/protocol/generated/alignment-params';
import type { Document, Feature, Region } from '@shared/protocol/generated/document-model';
import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';
import type { BlobRef, JsonValue } from '@shared/protocol/wireTypes';

import type { ObjectRef } from '../../state/objectSelectionStore';

export const ROLES: readonly InputRole[] = ['primary', 'secondary', 'tertiary'];

export type SlotInput =
  | { type: 'feature'; feature: string }
  | { type: 'region'; region: string }
  /** Triangles stored with a committed alignment (edited again). */
  | { type: 'faces'; faces: BlobRef }
  /** The working selection at the time it was taken. */
  | { type: 'selection'; faces: Uint32Array; scanKey: string };

export type Slots = Readonly<Record<InputRole, SlotInput | null>>;

export const EMPTY_SLOTS: Slots = { primary: null, secondary: null, tertiary: null };

/** What an input contributes to the frame; `surface` is decided by fitting the triangles. */
export type InputShape = 'plane' | 'axis' | 'point' | 'surface';

export type SlotProblem =
  | 'missing'
  | 'unknown'
  | 'unsupported'
  | 'pointAsPrimary'
  | 'duplicate'
  | 'tooFewFaces'
  | 'staleSelection';

type DocumentLike = Pick<Document, 'features' | 'regions'>;

const FIT_SHAPES: Readonly<Record<string, InputShape>> = {
  plane: 'plane',
  cylinder: 'axis',
  cone: 'axis',
  torus: 'axis',
  sphere: 'point',
};

const REFERENCE_SHAPES: Readonly<Record<string, InputShape>> = {
  offsetPlane: 'plane',
  midPlane: 'plane',
  planeThroughAxis: 'plane',
  axisFromPlanes: 'axis',
};

function field(value: JsonValue | undefined, key: string): JsonValue | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value[key]
    : undefined;
}

function text(value: JsonValue | undefined): string {
  return typeof value === 'string' ? value : '';
}

function featureShape(feature: Feature): InputShape | null {
  if (feature.type === 'fit') return FIT_SHAPES[text(field(feature.params, 'kind'))] ?? null;
  if (feature.type === 'reference') {
    const definition = field(feature.params, 'definition');
    return REFERENCE_SHAPES[text(field(definition, 'type'))] ?? null;
  }
  return null;
}

function regionShape(region: Region): InputShape | null {
  return FIT_SHAPES[region.kind] ?? null;
}

/** The shape of an input, null when it cannot serve as a datum, undefined when it is gone. */
export function inputShape(
  input: SlotInput,
  document: DocumentLike,
): InputShape | null | undefined {
  switch (input.type) {
    case 'feature': {
      const feature = document.features.find((item) => item.id === input.feature);
      if (!feature || feature.suppressed) return undefined;
      return featureShape(feature);
    }
    case 'region': {
      const region = document.regions.items.find((item) => item.id === input.region);
      return region ? regionShape(region) : undefined;
    }
    case 'faces':
    case 'selection':
      return 'surface';
  }
}

/** Identity of an input, to find the same face used twice. */
export function inputKey(input: SlotInput): string {
  switch (input.type) {
    case 'feature':
      return `feature:${input.feature}`;
    case 'region':
      return `region:${input.region}`;
    case 'faces':
      return `faces:${input.faces}`;
    case 'selection':
      return `selection:${input.scanKey}:${input.faces.length}:${input.faces[0] ?? ''}:${input.faces.at(-1) ?? ''}`;
  }
}

export function slotProblems(
  slots: Slots,
  document: DocumentLike,
  scanKey: string | null,
): Partial<Record<InputRole, SlotProblem>> {
  const problems: Partial<Record<InputRole, SlotProblem>> = {};
  const seen = new Set<string>();
  for (const role of ROLES) {
    const input = slots[role];
    if (!input) {
      if (role !== 'tertiary') problems[role] = 'missing';
      continue;
    }
    const shape = inputShape(input, document);
    const key = inputKey(input);
    if (shape === undefined) problems[role] = 'unknown';
    else if (shape === null) problems[role] = 'unsupported';
    else if (role === 'primary' && shape === 'point') problems[role] = 'pointAsPrimary';
    else if (seen.has(key)) problems[role] = 'duplicate';
    else if (input.type === 'selection' && input.scanKey !== scanKey)
      problems[role] = 'staleSelection';
    else if (input.type === 'selection' && input.faces.length < MIN_FIT_FACES)
      problems[role] = 'tooFewFaces';
    seen.add(key);
  }
  return problems;
}

export function isComplete(problems: Partial<Record<InputRole, SlotProblem>>): boolean {
  return Object.keys(problems).length === 0;
}

/** Put an input into a slot; returns the slots and the slot to fill next. */
export function assignInput(
  slots: Slots,
  role: InputRole,
  input: SlotInput | null,
): { slots: Slots; next: InputRole } {
  const updated = { ...slots, [role]: input };
  if (!input) return { slots: updated, next: role };
  const start = ROLES.indexOf(role);
  const following = [...ROLES.slice(start + 1), ...ROLES.slice(0, start)];
  return { slots: updated, next: following.find((item) => !updated[item]) ?? role };
}

/** An object picked in the tree or viewport as an input, if it can be one. */
export function inputFromObject(ref: ObjectRef, document: DocumentLike): SlotInput | null {
  if (ref.kind === 'feature') {
    const feature = document.features.find((item) => item.id === ref.id);
    return feature && featureShape(feature) ? { type: 'feature', feature: ref.id } : null;
  }
  if (ref.kind === 'region') {
    const region = document.regions.items.find((item) => item.id === ref.id);
    return region && regionShape(region) ? { type: 'region', region: ref.id } : null;
  }
  return null;
}

/** Objects selected before the tool opened fill the slots in order (at most three). */
export function slotsFromObjects(refs: readonly ObjectRef[], document: DocumentLike): Slots {
  const inputs = refs.flatMap((ref) => inputFromObject(ref, document) ?? []);
  return {
    primary: inputs[0] ?? null,
    secondary: inputs[1] ?? null,
    tertiary: inputs[2] ?? null,
  };
}

/** The slot as `alignment.preview` expects it. */
export function previewSlot(input: SlotInput | null): AlignmentSlot | null {
  if (!input) return null;
  return input.type === 'selection' ? { type: 'selection', faces: input.faces } : input;
}

function storedInput(value: JsonValue | undefined): SlotInput | null {
  const text = (key: string): string | null => {
    const item = field(value, key);
    return typeof item === 'string' && item.length > 0 ? item : null;
  };
  switch (field(value, 'type')) {
    case 'feature': {
      const feature = text('feature');
      return feature ? { type: 'feature', feature } : null;
    }
    case 'region': {
      const region = text('region');
      return region ? { type: 'region', region } : null;
    }
    case 'faces': {
      const faces = text('faces');
      return faces ? { type: 'faces', faces: faces as BlobRef } : null;
    }
    default:
      return null;
  }
}

/** The inputs of a committed faces alignment (`Alignment.params`). */
export function slotsFromParams(params: JsonValue): Slots {
  return {
    primary: storedInput(field(params, 'primary')),
    secondary: storedInput(field(params, 'secondary')),
    tertiary: storedInput(field(params, 'tertiary')),
  };
}
