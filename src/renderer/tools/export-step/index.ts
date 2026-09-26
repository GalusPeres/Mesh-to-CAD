import { FileOutput } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'export-step',
  kind: 'panel',
  status: 'planned',
  stages: ['inspect'],
  group: 'export',
  icon: FileOutput,
  primary: true,
  shortcut: { key: 'E', ctrl: true },
};
