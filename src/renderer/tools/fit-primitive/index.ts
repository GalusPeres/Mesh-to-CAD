import { Cylinder } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { FitPrimitivePanel } from './FitPrimitivePanel';

export const tool: ToolDefinition = {
  id: 'fit-primitive',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'fit',
  icon: Cylinder,
  primary: true,
  shortcut: { key: 'A' },
  edits: ['fit'],
  availability: ({ snapshot }) =>
    snapshot?.document.scan
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:fitPrimitive.noScan' },
  Panel: FitPrimitivePanel,
};
