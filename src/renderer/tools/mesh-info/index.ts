import { Info } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'mesh-info',
  kind: 'panel',
  status: 'planned',
  stages: ['prepare'],
  group: 'analysis',
  icon: Info,
};
