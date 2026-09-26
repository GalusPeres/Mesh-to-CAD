import { Gauge } from 'lucide-react';

import type { AppCommand } from '../app/commands/types';
import { openTool } from '../tools/framework/toolActions';
import { viewStore } from '../state/viewStore';
import { deviationStore, deviationValues, setDeviationVisible } from './deviationStore';

const hasMap = () => deviationValues() !== null && deviationStore.getState().summary !== null;

export const commands: readonly AppCommand[] = [
  {
    id: 'view.deviation',
    label: 'inspection:deviation.toggle',
    icon: Gauge,
    shortcuts: [{ key: 'D' }],
    scope: 'viewport',
    placement: { menu: 'view', group: 4, order: 1 },
    isChecked: () => hasMap() && viewStore.getState().deviationVisible,
    // Without a map, D opens the deviation tool, which computes one.
    run: () => {
      if (hasMap()) setDeviationVisible(!viewStore.getState().deviationVisible);
      else void openTool('deviation');
    },
  },
];
