import { Wrench } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'mesh-repair',
  kind: 'panel',
  status: 'planned',
  stages: ['prepare'],
  group: 'mesh',
  icon: Wrench,
  primary: true,
};
