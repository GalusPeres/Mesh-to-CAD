import { BoxSelect } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';

/** Selection mode: select the triangles inside a screen rectangle. It stays active while a panel tool is open. */
export const tool: ToolDefinition = {
  id: 'select-rectangle',
  kind: 'selection',
  status: 'ready',
  stages: ['prepare', 'align', 'model'],
  group: 'selection',
  icon: BoxSelect,
  availability: scanRequired,
};
