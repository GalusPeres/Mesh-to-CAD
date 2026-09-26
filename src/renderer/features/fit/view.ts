import { Cylinder } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'fit'> = {
  type: 'fit',
  icon: Cylinder,
  editTool: 'fit-primitive',
  baseName: (params, t) => t(`features:fit.kinds.${params.kind}`),
};
