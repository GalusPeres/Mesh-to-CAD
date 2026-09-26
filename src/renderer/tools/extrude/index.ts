import { ArrowUpFromDot } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'extrude',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'solid',
  icon: ArrowUpFromDot,
  primary: true,
  shortcut: { key: 'E' },
  edits: ['extrude'],
};
