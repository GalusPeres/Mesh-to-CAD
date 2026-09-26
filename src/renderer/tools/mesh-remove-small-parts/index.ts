import { Eraser } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'mesh-remove-small-parts',
  kind: 'panel',
  status: 'planned',
  stages: ['prepare'],
  group: 'mesh',
  icon: Eraser,
};
