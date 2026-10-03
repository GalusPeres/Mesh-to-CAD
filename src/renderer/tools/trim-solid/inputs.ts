// What "Zuschneiden" cuts: open surfaces (freeform nets and patches), planes and
// bodies, and which of them a new trim starts with.

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { TrimSolidParams } from '@shared/protocol/generated/feature-trim-solid';

import type { ObjectRef } from '../../state/objectSelectionStore';
import { ORIGIN_PLANES, availableBodies, isPlane, usableFeatures } from '../extrude/solid/model';

type Snapshot = Pick<DocumentSnapshot, 'document' | 'status'>;

export type InputKind = 'surfaces' | 'planes' | 'bodies';
export type TrimInputs = Pick<TrimSolidParams, InputKind>;

/** Feature types whose result can be an open surface (a closed one is a body). */
const SURFACE_TYPES = new Set(['freeformNet', 'freeformPatch', 'autoSurface']);

export interface TrimCandidates {
  surfaces: string[];
  /** Fitted and constructed planes first, the origin planes last. */
  planes: string[];
  bodies: string[];
}

export function trimCandidates(snapshot: Snapshot, editTarget: string | null): TrimCandidates {
  const bodies = availableBodies(snapshot, editTarget).map((body) => body.id);
  const surfaces = usableFeatures(
    snapshot,
    (feature) => SURFACE_TYPES.has(feature.type) && !bodies.includes(feature.id),
    editTarget,
  );
  const planes = [...usableFeatures(snapshot, isPlane, editTarget), ...ORIGIN_PLANES];
  return { surfaces, planes, bodies };
}

/** The objects chosen in the tree that can be cut, else the newest open surface. */
export function initialInputs(
  candidates: TrimCandidates,
  selected: readonly ObjectRef[],
): TrimInputs {
  const ids = new Set(selected.map((ref) => ref.id));
  const inputs = {
    surfaces: candidates.surfaces.filter((id) => ids.has(id)),
    planes: candidates.planes.filter((id) => ids.has(id)),
    bodies: candidates.bodies.filter((id) => ids.has(id)),
  };
  const newest = candidates.surfaces.at(-1);
  if (inputs.surfaces.length + inputs.planes.length + inputs.bodies.length === 0 && newest)
    inputs.surfaces = [newest];
  return inputs;
}

/** Add or remove one input, keeping the candidates' order. */
export function toggleInput(
  inputs: TrimInputs,
  kind: InputKind,
  id: string,
  order: readonly string[],
): TrimInputs {
  const chosen = new Set(inputs[kind]);
  if (chosen.has(id)) chosen.delete(id);
  else chosen.add(id);
  return { ...inputs, [kind]: order.filter((candidate) => chosen.has(candidate)) };
}

export function inputCount(inputs: TrimInputs): number {
  return inputs.surfaces.length + inputs.planes.length + inputs.bodies.length;
}
