import { Info } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { scanAvailability } from '../mesh-repair/scanEdit/scanEditModel';
import { InfoPanel } from './InfoPanel';

export const tool: ToolDefinition = {
  id: 'mesh-info',
  kind: 'panel',
  status: 'ready',
  stages: ['prepare'],
  group: 'analysis',
  icon: Info,
  availability: scanAvailability,
  Panel: InfoPanel,
};
