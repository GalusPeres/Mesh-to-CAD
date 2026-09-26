import { Shapes } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';
import { SegmentPanel } from './SegmentPanel';

export const tool: ToolDefinition = {
  id: 'segment',
  kind: 'panel',
  status: 'ready',
  stages: ['align', 'model'],
  group: 'regions',
  icon: Shapes,
  primary: true,
  availability: scanRequired,
  Panel: SegmentPanel,
};
