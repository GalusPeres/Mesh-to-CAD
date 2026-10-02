import { Grid2x2Check } from 'lucide-react';

import { statValue, statusOfParams } from '../freeform-patch/statusOf';
import type { FeatureView } from '../types';
import { FreeformNetProperties } from './FreeformNetProperties';

export const featureView: FeatureView<'freeformNet'> = {
  type: 'freeformNet',
  icon: Grid2x2Check,
  editTool: 'freeform-net',
  summary: (params, format, t) => {
    const status = statusOfParams(params);
    const faces = statValue(status, 'patches');
    if (faces === null) return t('features:freeformNet.name');
    const shape = statValue(status, 'closed') === 1 ? 'solid' : 'openSurface';
    return t('features:freeformNet.summary', {
      faces: format.count(faces),
      shape: t(`features:freeformNet.shapes.${shape}`),
    });
  },
  Properties: FreeformNetProperties,
};
