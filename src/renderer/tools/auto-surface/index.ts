import { Grid3x3 } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';
import { AutoSurfacePanel } from './AutoSurfacePanel';

export const tool: ToolDefinition = {
  id: 'auto-surface',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'freeform',
  icon: Grid3x3,
  edits: ['autoSurface'],
  availability: scanRequired,
  Panel: AutoSurfacePanel,
};
