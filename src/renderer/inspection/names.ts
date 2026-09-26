// Display names of bodies and body faces, numbered like the project tree.

import type { TFunction } from 'i18next';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { featureNames } from '../features/registry';

/** "Körper 1", "Körper 2" in the order of the document status (as in the tree). */
export function bodyNames(snapshot: DocumentSnapshot | null, t: TFunction): Map<string, string> {
  const bodies = snapshot?.status.bodies ?? [];
  return new Map(
    bodies.map((body, index) => [body.id, t('inspection:body', { number: index + 1 })]),
  );
}

export function faceName(bodyName: string, face: number, t: TFunction): string {
  return t('inspection:face', { body: bodyName, number: face + 1 });
}

export function documentFeatureNames(
  snapshot: DocumentSnapshot | null,
  t: TFunction,
): Map<string, string> {
  return featureNames(snapshot?.document.features ?? [], t);
}

/**
 * Name of the project for file names and the STEP product: the scan file name without
 * its extension, until projects carry their own name.
 */
export function projectName(snapshot: DocumentSnapshot | null, fallback: string): string {
  const file = snapshot?.document.scan?.source.fileName;
  if (!file) return fallback;
  const stem = file.replace(/\.[^.]+$/, '').trim();
  return stem || fallback;
}
