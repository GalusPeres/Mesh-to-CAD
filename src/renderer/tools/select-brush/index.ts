import { Paintbrush } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';

/** Selection mode: paint triangles under a ring cursor. It stays active while a panel tool is open. */
export const tool: ToolDefinition = {
  id: 'select-brush',
  kind: 'selection',
  status: 'ready',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: Paintbrush,
  shortcut: { key: 'B' },
  availability: scanRequired,
};
