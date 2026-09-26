import { Layers } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'loft',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'freeform',
  icon: Layers,
  edits: ['loft'],
};
