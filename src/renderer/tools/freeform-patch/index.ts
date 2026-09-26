import { Spline } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { FreeformPatchPanel } from './FreeformPatchPanel';

export const tool: ToolDefinition = {
  id: 'freeform-patch',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'freeform',
  icon: Spline,
  edits: ['freeformPatch'],
  availability: ({ snapshot }) =>
    snapshot?.document.scan
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:freeformPatch.noScan' },
  Panel: FreeformPatchPanel,
};
