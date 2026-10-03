import { Minimize2 } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { scanAvailability } from '../mesh-repair/scanEdit/scanEditModel';
import { DecimatePanel } from './DecimatePanel';

export const tool: ToolDefinition = {
  id: 'mesh-decimate',
  kind: 'panel',
  status: 'ready',
  stages: ['prepare'],
  group: 'mesh',
  icon: Minimize2,
  availability: scanAvailability,
  Panel: DecimatePanel,
};
