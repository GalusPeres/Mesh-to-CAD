import { ScanSearch } from 'lucide-react';

import { scanRequired } from '../../selection/availability';
import type { ToolDefinition } from '../framework/types';
import { RecognizePanel } from './RecognizePanel';

export const tool: ToolDefinition = {
  id: 'recognize',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'fit',
  icon: ScanSearch,
  primary: true,
  shortcut: { key: 'K' },
  availability: scanRequired,
  Panel: RecognizePanel,
};
