import { Layers } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { LoftPanel } from './LoftPanel';

export const tool: ToolDefinition = {
  id: 'loft',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'freeform',
  icon: Layers,
  edits: ['loft'],
  availability: ({ snapshot }) =>
    snapshot?.document.scan
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:loft.noScan' },
  Panel: LoftPanel,
};
