import { Wrench } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { RepairPanel } from './RepairPanel';
import { scanAvailability } from './scanEdit/scanEditModel';

export const tool: ToolDefinition = {
  id: 'mesh-repair',
  kind: 'panel',
  status: 'ready',
  stages: ['prepare'],
  group: 'mesh',
  icon: Wrench,
  primary: true,
  availability: scanAvailability,
  Panel: RepairPanel,
};
