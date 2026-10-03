import { Cylinder } from 'lucide-react';

import type { FeatureStatus } from '@shared/protocol/generated/document-results';
import type { FitParams } from '@shared/protocol/generated/feature-fit';

import { documentStore } from '../../state/documentStore';
import type { FeatureView } from '../types';
import { FitProperties } from './FitProperties';
import { fitSummary } from './fitStats';

/**
 * The status of the feature whose parameters these are. `summary` receives only
 * the parameters, which are the objects of the document snapshot, so the feature
 * is found by identity.
 */
function statusOf(params: FitParams): FeatureStatus | undefined {
  const snapshot = documentStore.getState().snapshot;
  const feature = snapshot?.document.features.find((item) => (item.params as unknown) === params);
  return feature ? snapshot?.status.features[feature.id] : undefined;
}

export const featureView: FeatureView<'fit'> = {
  type: 'fit',
  icon: Cylinder,
  editTool: 'fit-primitive',
  baseName: (params, t) => t(`features:fit.kinds.${params.kind}`),
  summary: (params, format, t) => fitSummary(params, statusOf(params), format, t),
  Properties: FitProperties,
};
