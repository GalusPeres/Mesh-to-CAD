import { FileDown } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'export-stl',
  kind: 'panel',
  status: 'planned',
  stages: ['inspect'],
  group: 'export',
  icon: FileDown,
};
