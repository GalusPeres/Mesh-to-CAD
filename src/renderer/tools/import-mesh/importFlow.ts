// Every way a file enters the application: Datei > Scan importieren, the empty
// state, the recent list and files dropped onto the window. The main process
// loads the file; a scan opens the import panel, a project becomes current.

import type { Canceled, RawResponse } from '@shared/bridge';

import { i18n } from '../../i18n';
import { KernelFailure } from '../../kernel/KernelFailure';
import { confirmUnsavedChanges, projectOpened, reportFailure } from '../../project/fileActions';
import { isLoadResult } from '../../project/loadResult';
import { openTool } from '../framework/toolActions';

const PROJECT_EXTENSION = '.m2c';

/** Show the file dialog; the main process loads the chosen file into a pending import. */
export async function importScanWithDialog(): Promise<void> {
  const response = await window.m2c.files.run(
    'openMesh',
    {},
    {
      title: i18n.t('tools:importMesh.dialogTitle'),
      filterName: i18n.t('tools:importMesh.filterName'),
    },
  );
  handleImportResponse(response);
}

/**
 * Open the import panel with the report of `mesh.import`, or make a project
 * current that the main process opened (`project.load`). A project that arrives
 * here was opened without asking about unsaved changes, so undo keeps the way
 * back to the document it replaced.
 */
export function handleImportResponse(response: RawResponse | Canceled): void {
  if ('canceled' in response) return;
  if (!response.ok) {
    reportFailure(new KernelFailure(response.error));
    return;
  }
  if (isLoadResult(response.result)) {
    projectOpened(response.result, { keepHistory: true });
    return;
  }
  void openTool('import-mesh', response.result);
}

/**
 * A file dropped onto the window. Before a project replaces the document, the
 * user is asked about unsaved changes; scans open the import panel (an import
 * can be undone, so nothing is lost there).
 */
export async function openDroppedFile(file: File): Promise<void> {
  if (!file.name.toLowerCase().endsWith(PROJECT_EXTENSION)) {
    handleImportResponse(await window.m2c.files.dropped(file));
    return;
  }
  if (!(await confirmUnsavedChanges())) return;
  const response = await window.m2c.files.dropped(file);
  if (response.ok && isLoadResult(response.result)) {
    projectOpened(response.result, { keepHistory: false });
  } else {
    handleImportResponse(response);
  }
}
