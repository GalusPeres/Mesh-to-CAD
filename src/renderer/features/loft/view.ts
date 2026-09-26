import { Layers } from 'lucide-react';

import { withOperation } from '../extrude/summary';
import type { FeatureView } from '../types';
import { LoftProperties } from './LoftProperties';

const GLOBAL_AXES = new Set(['X', 'Y', 'Z']);

export const featureView: FeatureView<'loft'> = {
  type: 'loft',
  icon: Layers,
  editTool: 'loft',
  summary: (params, format, t) => {
    const text = t('features:loft.summary', {
      count: params.sectionCount,
      length: format.length(params.end - params.start),
    });
    const along = GLOBAL_AXES.has(params.path)
      ? t('features:loft.along', { axis: params.path, text })
      : text;
    return withOperation(along, params.operation, t);
  },
  Properties: LoftProperties,
};
