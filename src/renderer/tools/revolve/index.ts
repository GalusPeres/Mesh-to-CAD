import { RotateCwSquare } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { RevolvePanel } from './RevolvePanel';

export const tool: ToolDefinition = {
  id: 'revolve',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'solid',
  icon: RotateCwSquare,
  primary: true,
  shortcut: { key: 'R' },
  edits: ['revolve'],
  availability: ({ snapshot }) =>
    snapshot?.document.features.some((feature) => feature.type === 'sketch')
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:extrude.noSketch' },
  Panel: RevolvePanel,
};
