import { Ruler } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'measure',
  kind: 'panel',
  status: 'planned',
  stages: ['inspect'],
  group: 'inspect',
  icon: Ruler,
  shortcut: { key: 'M' },
};
