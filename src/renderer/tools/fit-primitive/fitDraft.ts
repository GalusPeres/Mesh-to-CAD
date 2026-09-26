// The fit tool's draft (type, fixed values, relation, options, removed snaps) and the
// pure rules around it: which values a type has, how fixing and releasing works, what
// the kernel receives, and how results are listed. The panel only wires these to React.

import type { TFunction } from 'i18next';

import type { FitFixedInput, FitParams, FitRelation } from '@shared/protocol/generated/feature-fit';
import type { PreviewParams } from '@shared/protocol/generated/fit';
import type { AppliedSnap, SnapId } from '@shared/protocol/generated/fitting-intent';
import type { FitAlternative } from '@shared/protocol/generated/fitting-pipeline';
import type { Primitive, PrimitiveKind } from '@shared/protocol/generated/fitting-primitives';

import type { Formatter } from '../../i18n/format';
import type { SnapListItem } from '../../ui/SnapList/SnapList';

export type KindChoice = PrimitiveKind | 'auto';
export type ValueName = 'offset' | 'radius' | 'halfAngleDeg' | 'majorRadius' | 'minorRadius';
export type VectorName = 'direction' | 'point';
export type Vec3 = readonly [number, number, number];

/** Kinds from the fewest to the most parameters, as the kernel orders them. */
export const PRIMITIVE_KINDS: readonly PrimitiveKind[] = [
  'plane',
  'sphere',
  'cylinder',
  'cone',
  'torus',
];

/** Scalar parameters of each kind, in panel order. */
export const VALUES_BY_KIND: Readonly<Record<PrimitiveKind, readonly ValueName[]>> = {
  plane: ['offset'],
  sphere: ['radius'],
  cylinder: ['radius'],
  cone: ['halfAngleDeg'],
  torus: ['majorRadius', 'minorRadius'],
};

/** Kinds that have a direction (plane normal or axis). */
export function hasDirection(kind: PrimitiveKind): boolean {
  return kind !== 'sphere';
}

/** Kinds with a point that can be fixed (plane offsets are fixed through `offset`). */
export function hasPoint(kind: PrimitiveKind): boolean {
  return kind !== 'plane';
}

export interface FitDraft {
  kind: KindChoice;
  robust: boolean;
  snap: boolean;
  fixed: FitFixedInput;
  relation: FitRelation | null;
  rejectedSnaps: SnapId[];
}

export const EMPTY_DRAFT: FitDraft = {
  kind: 'auto',
  robust: false,
  snap: true,
  fixed: {},
  relation: null,
  rejectedSnaps: [],
};

/** The draft of a stored fit feature (edit mode). */
export function draftOf(params: FitParams): FitDraft {
  const fixed: FitFixedInput = {};
  for (const [name, value] of Object.entries(params.fixed)) {
    if (value !== null) (fixed as Record<string, unknown>)[name] = value;
  }
  return {
    kind: params.kind,
    robust: params.robust,
    snap: params.snap,
    fixed,
    relation: params.relation,
    rejectedSnaps: [...params.rejectedSnaps],
  };
}

function fixedNames(kind: PrimitiveKind): Set<keyof FitFixedInput> {
  const names = new Set<keyof FitFixedInput>(VALUES_BY_KIND[kind]);
  if (hasDirection(kind)) names.add('direction');
  if (hasPoint(kind)) names.add('point');
  return names;
}

/** A new type keeps only the fixed values and the relation that still apply. */
export function withKind(draft: FitDraft, kind: KindChoice): FitDraft {
  if (kind === 'auto') return { ...draft, kind, fixed: {}, relation: null };
  const allowed = fixedNames(kind);
  const fixed: FitFixedInput = {};
  for (const [name, value] of Object.entries(draft.fixed)) {
    if (allowed.has(name as keyof FitFixedInput)) (fixed as Record<string, unknown>)[name] = value;
  }
  return { ...draft, kind, fixed, relation: hasDirection(kind) ? draft.relation : null };
}

/**
 * Fix a value of the shown type. Fixing belongs to a type, so an automatic choice
 * becomes that type first. A fixed direction replaces a relation.
 */
export function fixValue(
  draft: FitDraft,
  shown: PrimitiveKind,
  name: ValueName | VectorName,
  value: number | Vec3,
): FitDraft {
  const typed = draft.kind === 'auto' ? withKind(draft, shown) : draft;
  const relation = name === 'direction' ? null : typed.relation;
  return { ...typed, relation, fixed: { ...typed.fixed, [name]: value } };
}

/** Let the fit compute the value again. */
export function releaseValue(draft: FitDraft, name: ValueName | VectorName): FitDraft {
  const fixed = { ...draft.fixed };
  delete fixed[name];
  return { ...draft, fixed };
}

export function isFixed(draft: FitDraft, name: ValueName | VectorName): boolean {
  return draft.fixed[name] !== undefined && draft.fixed[name] !== null;
}

/** A relation of the direction; it replaces a fixed direction. */
export function withRelation(
  draft: FitDraft,
  shown: PrimitiveKind,
  relation: FitRelation | null,
): FitDraft {
  const typed = draft.kind === 'auto' && relation ? withKind(draft, shown) : draft;
  const fixed = { ...typed.fixed };
  if (relation) delete fixed.direction;
  return { ...typed, fixed, relation };
}

export function rejectSnap(draft: FitDraft, id: SnapId): FitDraft {
  if (draft.rejectedSnaps.includes(id)) return draft;
  return { ...draft, rejectedSnaps: [...draft.rejectedSnaps, id] };
}

export function previewParams(draft: FitDraft, faces: Uint32Array, scanKey: string): PreviewParams {
  return {
    faces,
    scanKey,
    kind: draft.kind,
    robust: draft.robust,
    fixed: draft.fixed,
    relation: draft.relation,
    snap: draft.snap,
    rejectedSnaps: draft.rejectedSnaps,
  };
}

/**
 * Parameters of the fit feature (the `FitInput` wire form). The automatic choice is
 * stored as the type the preview found, so a rebuild never changes the type.
 */
export function featureInput(
  draft: FitDraft,
  faces: Uint32Array,
  fitted: PrimitiveKind,
  sourceRegion: string | null = null,
): Record<string, unknown> {
  return {
    faces,
    sourceRegion,
    kind: draft.kind === 'auto' ? fitted : draft.kind,
    robust: draft.robust,
    fixed: draft.fixed,
    relation: draft.relation,
    snap: draft.snap,
    rejectedSnaps: draft.rejectedSnaps,
  };
}

/** A scalar value of a fitted primitive; offset is the signed distance from the origin. */
export function primitiveValue(primitive: Primitive, name: ValueName): number | null {
  switch (primitive.type) {
    case 'plane':
      return name === 'offset' ? dot(primitive.origin, primitive.normal) : null;
    case 'sphere':
    case 'cylinder':
      return name === 'radius' ? primitive.radius : null;
    case 'cone':
      return name === 'halfAngleDeg' ? (primitive.halfAngle * 180) / Math.PI : null;
    case 'torus':
      if (name === 'majorRadius') return primitive.majorRadius;
      return name === 'minorRadius' ? primitive.minorRadius : null;
  }
}

/** Direction and point of a fitted primitive (point: plane origin, axis point, apex, centre). */
export function primitiveVector(primitive: Primitive, name: VectorName): Vec3 | null {
  switch (primitive.type) {
    case 'plane':
      return name === 'direction' ? primitive.normal : primitive.origin;
    case 'sphere':
      return name === 'point' ? primitive.center : null;
    case 'cylinder':
      return name === 'direction' ? primitive.axis : primitive.origin;
    case 'cone':
      return name === 'direction' ? primitive.axis : primitive.apex;
    case 'torus':
      return name === 'direction' ? primitive.axis : primitive.center;
  }
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

export interface KindOption {
  value: KindChoice;
  /** RMS of this type over the selection; null if it was not tried or did not fit. */
  rms: number | null;
}

/**
 * Entries of the type selector: Automatisch first, then the tried types from the
 * lowest RMS up, then the types that were not tried in their usual order.
 */
export function kindOptions(alternatives: readonly FitAlternative[]): KindOption[] {
  const tried = [...alternatives].sort((a, b) => a.rms - b.rms);
  const rest = PRIMITIVE_KINDS.filter((kind) => !tried.some((item) => item.kind === kind));
  return [
    { value: 'auto', rms: null },
    ...tried.map((item) => ({ value: item.kind, rms: item.rms })),
    ...rest.map((kind) => ({ value: kind, rms: null })),
  ];
}

const AXES = ['X', 'Y', 'Z'] as const;

function plusMinus(
  format: Formatter,
  value: number,
  uncertainty: number,
  decimals: number,
): string {
  return `${format.number(value, decimals)} ± ${format.number(uncertainty, decimals)}`;
}

/** Rows of the SnapList for applied snaps ("Radius 8,000 mm", measured "7,987 ± 0,012"). */
export function snapItems(
  snaps: readonly AppliedSnap[],
  kind: PrimitiveKind,
  format: Formatter,
  t: TFunction,
): SnapListItem[] {
  return snaps.map((snap) => {
    if (snap.kind === 'direction') {
      const subject = kind === 'plane' ? 'normal' : 'axis';
      const relation = snap.value === 0 ? 'parallel' : 'perpendicular';
      return {
        id: snap.id,
        text: t(`tools:fitPrimitive.snaps.${subject}.${relation}`, { axis: snap.target ?? '' }),
        measured: `${plusMinus(format, snap.measured, snap.uncertainty, 2)}°`,
      };
    }
    const value = snap.kind === 'angle' ? format.angle(snap.value) : format.length(snap.value);
    const measured =
      snap.kind === 'angle'
        ? `${plusMinus(format, snap.measured, snap.uncertainty, 2)}°`
        : plusMinus(format, snap.measured, snap.uncertainty, 3);
    return { id: snap.id, text: t(`tools:fitPrimitive.snaps.${snap.id}`, { value }), measured };
  });
}

/** The global axis a direction is exactly parallel to (snapped or fixed), if any. */
export function parallelAxis(direction: Vec3): (typeof AXES)[number] | null {
  const index = direction.findIndex((component) => Math.abs(Math.abs(component) - 1) < 1e-9);
  return index >= 0 ? (AXES[index] ?? null) : null;
}

/** The global axis a direction is exactly perpendicular to, when it is not parallel to one. */
export function perpendicularAxis(direction: Vec3): (typeof AXES)[number] | null {
  if (parallelAxis(direction)) return null;
  const index = direction.findIndex((component) => Math.abs(component) < 1e-9);
  return index >= 0 ? (AXES[index] ?? null) : null;
}

/**
 * The working selection after a committed fit: without the triangles the fit used
 * (`used[i]` is 1 for `faces[i]`), unless the setting keeps it. Null keeps the selection.
 */
export function selectionAfterFit(
  selected: Uint32Array,
  faces: Uint32Array,
  used: Uint8Array,
  clearAfterFit: boolean,
): Uint32Array | null {
  if (!clearAfterFit) return null;
  const remove = new Set(faces.filter((_face, index) => used[index] === 1));
  return selected.filter((face) => !remove.has(face));
}
