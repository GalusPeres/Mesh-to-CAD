import { Layers } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'loft'> = {
  type: 'loft',
  icon: Layers,
  editTool: 'loft',
};
