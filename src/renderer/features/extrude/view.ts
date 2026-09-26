import { ArrowUpFromDot } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'extrude'> = {
  type: 'extrude',
  icon: ArrowUpFromDot,
  editTool: 'extrude',
};
