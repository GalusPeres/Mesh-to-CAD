import { Scissors } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'trim',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'solid',
  icon: Scissors,
  edits: ['trim'],
};
