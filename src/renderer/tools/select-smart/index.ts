import { Wand } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';

/** Selection mode: grow the surface under the cursor in the kernel (regions.grow). It stays active while a panel tool is open. */
export const tool: ToolDefinition = {
  id: 'select-smart',
  kind: 'selection',
  status: 'ready',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: Wand,
  shortcut: { key: 'W' },
  availability: scanRequired,
};
