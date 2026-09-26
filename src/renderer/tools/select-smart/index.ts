import { Wand } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'select-smart',
  kind: 'selection',
  status: 'planned',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: Wand,
  shortcut: { key: 'W' },
};
