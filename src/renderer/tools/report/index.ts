import { FileText } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'report',
  kind: 'action',
  status: 'planned',
  stages: ['inspect'],
  group: 'inspect',
  icon: FileText,
};
