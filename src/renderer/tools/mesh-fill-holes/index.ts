import { CircleDashed } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'mesh-fill-holes',
  kind: 'panel',
  status: 'planned',
  stages: ['prepare'],
  group: 'mesh',
  icon: CircleDashed,
};
