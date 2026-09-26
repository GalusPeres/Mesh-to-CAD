import { Gauge } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'deviation',
  kind: 'panel',
  status: 'planned',
  stages: ['inspect'],
  group: 'inspect',
  icon: Gauge,
  primary: true,
};
