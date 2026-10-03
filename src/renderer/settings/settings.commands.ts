import { Settings } from 'lucide-react';

import type { AppCommand } from '../app/commands/types';
import { openDialog } from './appDialogStore';

export const commands: readonly AppCommand[] = [
  {
    id: 'app.settings',
    label: 'common:commands.settings',
    icon: Settings,
    shortcuts: [{ key: ',', ctrl: true }],
    placement: { menu: 'edit', group: 9, order: 1 },
    run: () => openDialog('settings'),
  },
];
