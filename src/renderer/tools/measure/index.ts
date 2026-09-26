import { Ruler } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { MeasurePanel } from './MeasurePanel';

export const tool: ToolDefinition = {
  id: 'measure',
  kind: 'panel',
  status: 'ready',
  stages: ['inspect'],
  group: 'inspect',
  icon: Ruler,
  primary: true,
  shortcut: { key: 'M' },
  availability: ({ snapshot }) =>
    snapshot?.document.scan
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:measure.noScan' },
  Panel: MeasurePanel,
};
