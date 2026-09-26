import { Spline } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'freeform-patch',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'freeform',
  icon: Spline,
  edits: ['freeformPatch'],
};
