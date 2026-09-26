import { FileInput } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { ImportPanel } from './ImportPanel';

/** Opened with the report of `mesh.import` after the file dialog or a drop; not in the tool row. */
export const tool: ToolDefinition = {
  id: 'import-mesh',
  kind: 'panel',
  status: 'ready',
  stages: [],
  group: 'mesh',
  icon: FileInput,
  Panel: ImportPanel,
};
