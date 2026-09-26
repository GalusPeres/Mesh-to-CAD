import { Paintbrush } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'select-brush',
  kind: 'selection',
  status: 'planned',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: Paintbrush,
  shortcut: { key: 'B' },
};
