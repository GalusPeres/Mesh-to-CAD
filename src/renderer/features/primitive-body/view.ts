import { Box } from 'lucide-react';

import { withOperation } from '../extrude/summary';
import type { FeatureView } from '../types';

export const featureView: FeatureView<'primitiveBody'> = {
  type: 'primitiveBody',
  icon: Box,
  editTool: 'primitive-body',
  summary: (params, format, t) => {
    const extent = params.extent;
    const text =
      extent.type === 'manual'
        ? format.length(extent.length)
        : extent.margin > 0
          ? t('features:primitiveBody.fromScanMargin', { margin: format.length(extent.margin) })
          : t('features:primitiveBody.fromScan');
    return withOperation(text, params.operation, t);
  },
};
