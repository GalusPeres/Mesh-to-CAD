import { Waves } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'mesh-smooth',
  kind: 'panel',
  status: 'planned',
  stages: ['prepare'],
  group: 'mesh',
  icon: Waves,
};
