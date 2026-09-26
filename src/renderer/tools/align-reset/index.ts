import { RotateCcw } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'align-reset',
  kind: 'action',
  status: 'planned',
  stages: ['align'],
  group: 'align',
  icon: RotateCcw,
};
