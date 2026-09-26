import { PenTool } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'sketch'> = {
  type: 'sketch',
  icon: PenTool,
  editTool: 'section-sketch',
};
