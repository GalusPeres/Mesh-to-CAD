import { Gauge } from 'lucide-react';

import type { ToolDefinition } from '../framework/types';
import { DeviationPanel } from './DeviationPanel';

/** The colour map of the scan against the bodies; `D` toggles its display (view command). */
export const tool: ToolDefinition = {
  id: 'deviation',
  kind: 'panel',
  status: 'ready',
  stages: ['inspect'],
  group: 'inspect',
  icon: Gauge,
  primary: true,
  availability: ({ snapshot }) =>
    snapshot?.status.bodies.length
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:deviation.noBody' },
  Panel: DeviationPanel,
};
