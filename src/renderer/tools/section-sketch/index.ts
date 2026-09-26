import { PenTool } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'section-sketch',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'sketch',
  icon: PenTool,
  primary: true,
  shortcut: { key: 'S' },
  edits: ['sketch'],
  confirmDiscard: true,
};
