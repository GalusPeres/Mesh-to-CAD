import type { FeatureStatus } from '@shared/protocol/generated/document-results';

import { documentStore } from '../../state/documentStore';

/**
 * The status of the feature whose parameters these are. A summary receives only the
 * parameters, which are objects of the document snapshot, so the feature is found
 * by identity.
 */
export function statusOfParams(params: unknown): FeatureStatus | undefined {
  const snapshot = documentStore.getState().snapshot;
  const feature = snapshot?.document.features.find((item) => (item.params as unknown) === params);
  return feature ? snapshot?.status.features[feature.id] : undefined;
}

export function statValue(status: FeatureStatus | undefined, key: string): number | null {
  const value = status?.stats[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
