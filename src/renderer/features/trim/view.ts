import { Scissors } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'trim'> = {
  type: 'trim',
  icon: Scissors,
  editTool: 'trim',
};
