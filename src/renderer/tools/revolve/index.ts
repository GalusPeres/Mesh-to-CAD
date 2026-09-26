import { RotateCwSquare } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'revolve',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'solid',
  icon: RotateCwSquare,
  primary: true,
  shortcut: { key: 'R' },
  edits: ['revolve'],
};
