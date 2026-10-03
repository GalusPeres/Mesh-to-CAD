import { FilletIcon } from '../../ui/icons/customIcons';
import type { ToolDefinition } from '../framework/types';
import { FilletPanel } from './FilletPanel';

export const tool: ToolDefinition = {
  id: 'fillet',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'solid',
  icon: FilletIcon,
  edits: ['fillet'],
  confirmDiscard: true,
  availability: ({ snapshot }) =>
    snapshot?.status.bodies.length
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:trim.noBody' },
  Panel: FilletPanel,
};
