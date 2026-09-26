import { Crosshair } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { AlignFacesPanel } from './AlignFacesPanel';

export const tool: ToolDefinition = {
  id: 'align-faces',
  kind: 'panel',
  status: 'ready',
  stages: ['align'],
  group: 'align',
  icon: Crosshair,
  primary: true,
  confirmDiscard: true,
  availability: ({ snapshot }) =>
    snapshot?.document.scan
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:alignAuto.noScan' },
  Panel: AlignFacesPanel,
};
