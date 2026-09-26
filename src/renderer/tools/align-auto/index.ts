import { Axis3d } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'align-auto',
  kind: 'panel',
  status: 'planned',
  stages: ['align'],
  group: 'align',
  icon: Axis3d,
  primary: true,
};
