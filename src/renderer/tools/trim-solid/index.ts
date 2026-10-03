import { Crop } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { trimCandidates } from './inputs';
import { TrimSolidPanel } from './TrimSolidPanel';

export const tool: ToolDefinition = {
  id: 'trim-solid',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'solid',
  icon: Crop,
  edits: ['trimSolid'],
  availability: ({ snapshot }) => {
    const candidates = snapshot ? trimCandidates(snapshot, null) : null;
    return candidates && candidates.surfaces.length + candidates.bodies.length > 0
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:trimSolid.nothing' };
  },
  Panel: TrimSolidPanel,
};
