import { FileInput } from 'lucide-react';

import type { AppCommand } from '../../app/commands/types';
import { importScanWithDialog } from './importFlow';

export const commands: readonly AppCommand[] = [
  {
    id: 'file.importScan',
    label: 'tools:importMesh.command',
    icon: FileInput,
    shortcuts: [{ key: 'I', ctrl: true }],
    inTextFields: true,
    placement: { menu: 'file', group: 2, order: 1 },
    run: importScanWithDialog,
  },
];
