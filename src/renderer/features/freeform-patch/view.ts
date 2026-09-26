import { Spline } from 'lucide-react';

import type { FeatureView } from '../types';
import { PatchProperties } from './PatchProperties';
import { statValue, statusOfParams } from './statusOf';

export const featureView: FeatureView<'freeformPatch'> = {
  type: 'freeformPatch',
  icon: Spline,
  editTool: 'freeform-patch',
  summary: (params, format, t) => {
    const rms = statValue(statusOfParams(params), 'freeform.stats.rms');
    if (rms !== null) return t('features:freeformPatch.summaryRms', { rms: format.length(rms) });
    return params.spans
      ? t('features:freeformPatch.spansValue', { u: params.spans[0], v: params.spans[1] })
      : t('features:freeformPatch.autoSpans');
  },
  Properties: PatchProperties,
};
