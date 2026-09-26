import { Shapes } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'segment',
  kind: 'panel',
  status: 'planned',
  stages: ['align', 'model'],
  group: 'regions',
  icon: Shapes,
  primary: true,
};
