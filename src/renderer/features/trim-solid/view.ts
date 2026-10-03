import { Crop } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'trimSolid'> = {
  type: 'trimSolid',
  icon: Crop,
  editTool: 'trim-solid',
  summary: (params, _format, t) =>
    t('features:trimSolid.summary', {
      count: params.surfaces.length + params.planes.length + params.bodies.length,
    }),
};
