import { Cylinder } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'fit-primitive',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'fit',
  icon: Cylinder,
  primary: true,
  shortcut: { key: 'A' },
  edits: ['fit'],
};
