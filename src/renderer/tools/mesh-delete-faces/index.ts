import { Trash2 } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'mesh-delete-faces',
  kind: 'action',
  status: 'planned',
  stages: ['prepare'],
  group: 'mesh',
  icon: Trash2,
  shortcut: { key: 'Delete' },
};
