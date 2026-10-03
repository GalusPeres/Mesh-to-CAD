import { Lasso } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';

/** Selection mode: select the triangles inside a freehand screen shape. It stays active while a panel tool is open. */
export const tool: ToolDefinition = {
  id: 'select-lasso',
  kind: 'selection',
  status: 'ready',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: Lasso,
  shortcut: { key: 'L' },
  availability: scanRequired,
};
