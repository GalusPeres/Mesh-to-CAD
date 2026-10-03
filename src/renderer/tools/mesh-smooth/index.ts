import { Waves } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { scanAvailability } from '../mesh-repair/scanEdit/scanEditModel';
import { SmoothPanel } from './SmoothPanel';

export const tool: ToolDefinition = {
  id: 'mesh-smooth',
  kind: 'panel',
  status: 'ready',
  stages: ['prepare'],
  group: 'mesh',
  icon: Waves,
  availability: scanAvailability,
  Panel: SmoothPanel,
};
