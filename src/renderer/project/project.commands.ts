import { FilePlus, FolderOpen, Save } from 'lucide-react';

import type { AppCommand } from '../app/commands/types';
import { documentStore } from '../state/documentStore';
import { newProject, openProject, saveProject, saveProjectAs } from './fileActions';

const hasScan = () => !!documentStore.getState().snapshot?.document.scan;

export const commands: readonly AppCommand[] = [
  {
    id: 'file.new',
    label: 'project:commands.new',
    icon: FilePlus,
    shortcuts: [{ key: 'N', ctrl: true }],
    inTextFields: true,
    placement: { menu: 'file', group: 1, order: 1 },
    run: newProject,
  },
  {
    id: 'file.openProject',
    label: 'project:commands.open',
    icon: FolderOpen,
    shortcuts: [{ key: 'O', ctrl: true }],
    inTextFields: true,
    placement: { menu: 'file', group: 1, order: 2 },
    run: openProject,
  },
  {
    id: 'file.save',
    label: 'project:commands.save',
    icon: Save,
    shortcuts: [{ key: 'S', ctrl: true }],
    inTextFields: true,
    placement: { menu: 'file', group: 3, order: 1 },
    isEnabled: hasScan,
    run: async () => {
      await saveProject();
    },
  },
  {
    id: 'file.saveAs',
    label: 'project:commands.saveAs',
    shortcuts: [{ key: 'S', ctrl: true, shift: true }],
    inTextFields: true,
    placement: { menu: 'file', group: 3, order: 2 },
    isEnabled: hasScan,
    run: async () => {
      await saveProjectAs();
    },
  },
];
