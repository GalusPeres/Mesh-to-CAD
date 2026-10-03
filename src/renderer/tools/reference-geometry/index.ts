import { PlaneIcon } from '../../ui/icons/customIcons';
import type { ToolDefinition } from '../framework/types';
import { ReferencePanel } from './ReferencePanel';

export const tool: ToolDefinition = {
  id: 'reference-geometry',
  kind: 'panel',
  status: 'ready',
  stages: ['model'],
  group: 'reference',
  icon: PlaneIcon,
  edits: ['reference'],
  Panel: ReferencePanel,
};
