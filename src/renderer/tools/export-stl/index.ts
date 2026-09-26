import { FileDown } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { ExportStlPanel } from './ExportStlPanel';

export const tool: ToolDefinition = {
  id: 'export-stl',
  kind: 'panel',
  status: 'ready',
  stages: ['inspect'],
  group: 'export',
  icon: FileDown,
  availability: ({ snapshot }) =>
    snapshot?.status.bodies.length
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:exportStl.noBody' },
  Panel: ExportStlPanel,
};
