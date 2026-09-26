import { CircleDashed } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { scanAvailability } from '../mesh-repair/scanEdit/scanEditModel';
import { FillHolesPanel } from './FillHolesPanel';

export const tool: ToolDefinition = {
  id: 'mesh-fill-holes',
  kind: 'panel',
  status: 'ready',
  stages: ['prepare'],
  group: 'mesh',
  icon: CircleDashed,
  availability: scanAvailability,
  Panel: FillHolesPanel,
};
