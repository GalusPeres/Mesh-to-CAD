import { i18n } from '../../i18n';
import { kernel } from '../../kernel/kernel';
import { reportFailure } from '../../project/fileActions';
import { clearSelection, selectedFaces } from '../../selection/api';
import { documentStore } from '../../state/documentStore';
import { showMessage } from '../../state/messageStore';

/**
 * Delete the selected triangles of the current scan (Entf in *Vorbereiten*).
 * The selection is sent with the key of the scan it was made on, so the kernel
 * refuses a selection that belongs to an older scan.
 */
export async function deleteSelectedFaces(): Promise<void> {
  const scan = documentStore.getState().snapshot?.document.scan;
  if (!scan) return;
  const faces = selectedFaces(scan.key);
  if (faces.length === 0) {
    showMessage('info', i18n.t('tools:meshDeleteFaces.nothingSelected'));
    return;
  }
  try {
    const result = await kernel().call('mesh.deleteFaces', { faces, scanKey: scan.key }).result;
    clearSelection();
    const deleted = result.counts.deletedFaces ?? faces.length;
    showMessage('success', i18n.t('tools:meshDeleteFaces.deleted', { count: deleted }));
  } catch (error) {
    reportFailure(error);
  }
}
