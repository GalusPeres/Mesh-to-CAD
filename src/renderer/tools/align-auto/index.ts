import { Axis3d } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { AlignAutoPanel } from './AlignAutoPanel';

export const tool: ToolDefinition = {
  id: 'align-auto',
  kind: 'panel',
  status: 'ready',
  stages: ['align'],
  group: 'align',
  icon: Axis3d,
  primary: true,
  availability: ({ snapshot }) =>
    snapshot?.document.scan
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:alignAuto.noScan' },
  Panel: AlignAutoPanel,
};
