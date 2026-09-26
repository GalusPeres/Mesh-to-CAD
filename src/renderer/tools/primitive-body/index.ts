import { Box } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'primitive-body',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'solid',
  icon: Box,
  edits: ['primitiveBody'],
};
