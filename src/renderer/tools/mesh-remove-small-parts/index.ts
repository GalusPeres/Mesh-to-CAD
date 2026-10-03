import { Eraser } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { scanAvailability } from '../mesh-repair/scanEdit/scanEditModel';
import { RemoveSmallPartsPanel } from './RemoveSmallPartsPanel';

export const tool: ToolDefinition = {
  id: 'mesh-remove-small-parts',
  kind: 'panel',
  status: 'ready',
  stages: ['prepare'],
  group: 'mesh',
  icon: Eraser,
  availability: scanAvailability,
  Panel: RemoveSmallPartsPanel,
};
