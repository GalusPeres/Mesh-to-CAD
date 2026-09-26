import { FilletIcon } from '../../ui/icons/customIcons';
import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'fillet',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'solid',
  icon: FilletIcon,
  edits: ['fillet'],
  confirmDiscard: true,
};
