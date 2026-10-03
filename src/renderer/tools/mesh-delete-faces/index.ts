import { Trash2 } from 'lucide-react';

import { toolStore } from '../../state/toolStore';
import type { ToolContext, ToolDefinition } from '../framework/types';
import { scanAvailability } from '../mesh-repair/scanEdit/scanEditModel';
import { deleteSelectedFaces } from './deleteSelectedFaces';

/** Entf deletes triangles only in *Vorbereiten*; elsewhere the key belongs to the tree. */
function availability(context: ToolContext) {
  if (toolStore.getState().stage !== 'prepare') {
    return { enabled: false, reasonKey: 'tools:meshDeleteFaces.onlyInPrepare' } as const;
  }
  return scanAvailability(context);
}

export const tool: ToolDefinition = {
  id: 'mesh-delete-faces',
  kind: 'action',
  status: 'ready',
  stages: ['prepare'],
  group: 'mesh',
  icon: Trash2,
  shortcut: { key: 'Delete' },
  availability,
  run: deleteSelectedFaces,
};
