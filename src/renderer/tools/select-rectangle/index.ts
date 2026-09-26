import { BoxSelect } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'select-rectangle',
  kind: 'selection',
  status: 'planned',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: BoxSelect,
};
