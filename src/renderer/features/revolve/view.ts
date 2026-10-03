import { RotateCwSquare } from 'lucide-react';

import { withOperation } from '../extrude/summary';
import type { FeatureView } from '../types';

export const featureView: FeatureView<'revolve'> = {
  type: 'revolve',
  icon: RotateCwSquare,
  editTool: 'revolve',
  summary: (params, format, t) => withOperation(format.angle(params.angleDeg), params.operation, t),
};
