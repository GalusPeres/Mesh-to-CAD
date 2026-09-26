import { SquaresUnite } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'combine'> = {
  type: 'combine',
  icon: SquaresUnite,
  editTool: 'combine',
  summary: (params, _format, t) =>
    `${t(`tools:extrude.solid.operations.${params.operation}`)}, ${t('features:combine.tools', {
      count: params.tools.length,
    })}`,
};
