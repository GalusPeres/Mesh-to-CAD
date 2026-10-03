import { Grid2x2Check } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';
import { FreeformNetPanel } from './FreeformNetPanel';

export const tool: ToolDefinition = {
  id: 'freeform-net',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'freeform',
  icon: Grid2x2Check,
  primary: true,
  shortcut: { key: 'N' },
  edits: ['freeformNet'],
  availability: scanRequired,
  confirmDiscard: true,
  keepDraftOnLeave: true,
  Panel: FreeformNetPanel,
};
