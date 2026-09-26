import { SquaresUnite } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'combine',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'solid',
  icon: SquaresUnite,
  edits: ['combine'],
};
