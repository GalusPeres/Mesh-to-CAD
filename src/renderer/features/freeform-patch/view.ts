import { Spline } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'freeformPatch'> = {
  type: 'freeformPatch',
  icon: Spline,
  editTool: 'freeform-patch',
};
