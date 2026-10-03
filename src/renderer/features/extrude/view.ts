import { ArrowUpFromDot } from 'lucide-react';

import type { FeatureView } from '../types';
import { withOperation } from './summary';

export const featureView: FeatureView<'extrude'> = {
  type: 'extrude',
  icon: ArrowUpFromDot,
  editTool: 'extrude',
  summary: (params, format, t) => {
    const extent = params.extent;
    let text: string;
    if (extent.type === 'toPlane') {
      text = t('features:extrude.toPlane');
    } else if (params.direction === 'symmetric') {
      text = t('features:extrude.symmetric', { length: format.length(extent.forward) });
    } else if (extent.backward > 0) {
      text = `${format.length(extent.forward)} / ${format.length(extent.backward)}`;
    } else {
      text = format.length(extent.forward);
    }
    return withOperation(text, params.operation, t);
  },
};
