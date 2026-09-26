import { FileOutput } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { ExportStepPanel } from './ExportStepPanel';

export const tool: ToolDefinition = {
  id: 'export-step',
  kind: 'panel',
  status: 'ready',
  stages: ['inspect'],
  group: 'export',
  icon: FileOutput,
  primary: true,
  shortcut: { key: 'E', ctrl: true },
  availability: ({ snapshot }) =>
    snapshot?.status.bodies.length
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:exportStep.noBody' },
  Panel: ExportStepPanel,
};
