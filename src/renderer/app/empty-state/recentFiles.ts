import type { RawResponse, RecentFile } from '@shared/bridge';

import { i18n } from '../../i18n';
import { KernelFailure } from '../../kernel/KernelFailure';
import { describeError } from '../../kernel/describeError';
import { showMessage } from '../../state/messageStore';
import { handleImportResponse } from '../../tools/import-mesh/importFlow';

/** The empty state lists at most this many files (docs/DESIGN.md 5.8). */
export const RECENT_LIMIT = 5;

/** Most recently opened first. */
export function recentRows(files: readonly RecentFile[], limit = RECENT_LIMIT): RecentFile[] {
  return [...files].sort((a, b) => b.openedAt - a.openedAt).slice(0, limit);
}

/**
 * Open a recent file. A scan goes through the import panel like any other scan; a
 * project replaces the (empty) document and arrives through `documentChanged`.
 */
export async function openRecent(file: RecentFile): Promise<void> {
  const response: RawResponse = await window.m2c.files.openRecent(file.id);
  if (file.kind === 'mesh') {
    handleImportResponse(response);
    return;
  }
  if (!response.ok) {
    const failure = new KernelFailure(response.error);
    showMessage('error', describeError(failure, i18n.t), failure.details);
  }
}
