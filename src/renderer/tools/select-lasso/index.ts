import { Lasso } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'select-lasso',
  kind: 'selection',
  status: 'planned',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: Lasso,
  shortcut: { key: 'L' },
};
