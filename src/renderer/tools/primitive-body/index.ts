import { Box } from 'lucide-react';

import { isBodyFit } from '../extrude/solid/model';
import type { ToolDefinition } from '../framework/types';
import { PrimitiveBodyPanel } from './PrimitiveBodyPanel';

export const tool: ToolDefinition = {
  id: 'primitive-body',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'solid',
  icon: Box,
  edits: ['primitiveBody'],
  availability: ({ snapshot }) =>
    snapshot?.document.features.some(isBodyFit)
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:primitiveBody.noFit' },
  Panel: PrimitiveBodyPanel,
};
