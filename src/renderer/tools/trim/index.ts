import { Scissors } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { TrimPanel } from './TrimPanel';

export const tool: ToolDefinition = {
  id: 'trim',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'solid',
  icon: Scissors,
  edits: ['trim'],
  availability: ({ snapshot }) =>
    snapshot?.status.bodies.length
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:trim.noBody' },
  Panel: TrimPanel,
};
