import { Crosshair } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'align-faces',
  kind: 'panel',
  status: 'planned',
  stages: ['align'],
  group: 'align',
  icon: Crosshair,
  primary: true,
};
