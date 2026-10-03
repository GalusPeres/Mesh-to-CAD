import { SquaresUnite } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { CombinePanel } from './CombinePanel';

export const tool: ToolDefinition = {
  id: 'combine',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'solid',
  icon: SquaresUnite,
  edits: ['combine'],
  availability: ({ snapshot }) =>
    (snapshot?.status.bodies.length ?? 0) >= 2
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:combine.twoBodies' },
  Panel: CombinePanel,
};
