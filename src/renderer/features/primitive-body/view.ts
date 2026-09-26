import { Box } from 'lucide-react';

import type { FeatureView } from '../types';

export const featureView: FeatureView<'primitiveBody'> = {
  type: 'primitiveBody',
  icon: Box,
  editTool: 'primitive-body',
};
