import { ArrowUpFromDot } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { ExtrudePanel } from './ExtrudePanel';

export const tool: ToolDefinition = {
  id: 'extrude',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'solid',
  icon: ArrowUpFromDot,
  primary: true,
  shortcut: { key: 'E' },
  edits: ['extrude'],
  availability: ({ snapshot }) =>
    snapshot?.document.features.some((feature) => feature.type === 'sketch')
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:extrude.noSketch' },
  Panel: ExtrudePanel,
};
