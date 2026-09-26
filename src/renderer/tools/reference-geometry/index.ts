import { PlaneIcon } from '../../ui/icons/customIcons';
import type { ToolDefinition } from '../framework/types';

export const tool: ToolDefinition = {
  id: 'reference-geometry',
  kind: 'panel',
  status: 'planned',
  stages: ['model'],
  group: 'reference',
  icon: PlaneIcon,
  edits: ['reference'],
};
