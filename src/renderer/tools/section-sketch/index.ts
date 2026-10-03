import { PenTool } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { SketchPanel } from './SketchPanel';

export const tool: ToolDefinition = {
  id: 'section-sketch',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'sketch',
  icon: PenTool,
  primary: true,
  shortcut: { key: 'S' },
  availability: ({ snapshot }) =>
    snapshot?.document.scan
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:sectionSketch.noScan' },
  Panel: SketchPanel,
  edits: ['sketch'],
  confirmDiscard: true,
};
