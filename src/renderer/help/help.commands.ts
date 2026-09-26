import { BookOpen, CircleHelp, Info, Keyboard } from 'lucide-react';

import type { AppCommand } from '../app/commands/types';
import { exclusiveJobRunning, jobStore } from '../state/jobStore';
import { openDialog } from '../settings/appDialogStore';
import { EXAMPLES, openExample } from './examples';
import { openHelp } from './openHelp';

const canImport = () => jobStore.getState().kernel.state === 'ready' && !exclusiveJobRunning();

export const commands: readonly AppCommand[] = [
  {
    id: 'help.tool',
    label: 'help:commands.help',
    icon: CircleHelp,
    shortcuts: [{ key: 'F1' }],
    inTextFields: true,
    placement: { menu: 'help', group: 1, order: 1 },
    run: () => openHelp(),
  },
  {
    id: 'help.gettingStarted',
    label: 'help:commands.gettingStarted',
    icon: BookOpen,
    placement: { menu: 'help', group: 1, order: 2 },
    run: () => openHelp('getting-started'),
  },
  {
    id: 'help.shortcuts',
    label: 'help:commands.shortcuts',
    icon: Keyboard,
    shortcuts: [{ key: '/', ctrl: true }],
    placement: { menu: 'help', group: 1, order: 3 },
    run: () => openDialog('shortcuts'),
  },
  ...EXAMPLES.map((example, index): AppCommand => ({
    id: `help.example.${example}`,
    label: `help:commands.example.${example}`,
    placement: { menu: 'help', group: 2, order: index },
    isEnabled: canImport,
    run: () => openExample(example),
  })),
  {
    id: 'help.about',
    label: 'common:commands.about',
    icon: Info,
    placement: { menu: 'help', group: 9, order: 1 },
    run: () => openDialog('about'),
  },
];
