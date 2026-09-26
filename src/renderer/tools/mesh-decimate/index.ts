import { Minimize2 } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'mesh-decimate',
  kind: 'panel',
  status: 'planned',
  stages: ['prepare'],
  group: 'mesh',
  icon: Minimize2,
};
