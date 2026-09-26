import type { Canceled, RawResponse } from '@shared/bridge';

import { i18n } from '../../i18n';
import { KernelFailure } from '../../kernel/KernelFailure';
import { describeError } from '../../kernel/describeError';
import { showMessage } from '../../state/messageStore';
import { openTool } from '../framework/toolActions';

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

/** Open the import panel with the report, or show why loading failed. */
export function handleImportResponse(response: RawResponse | Canceled): void {
  if ('canceled' in response) return;
  if (!response.ok) {
    const failure = new KernelFailure(response.error);
    showMessage('error', describeError(failure, i18n.t), failure.details);
    return;
  }
  void openTool('import-mesh', response.result);
}
