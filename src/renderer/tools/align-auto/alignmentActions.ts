import type { JsonValue } from '@shared/protocol/wireTypes';
import type { Alignment, AlignmentAdjust } from '@shared/protocol/generated/document-model';

import { kernel } from '../../kernel/kernel';
import { currentRevision, documentStore } from '../../state/documentStore';
import { NO_ADJUST } from './adjust';

export type AlignmentMethod = Alignment['method'];

/** The committed alignment, or null before a scan exists. */
export function committedAlignment(): Alignment | null {
  return documentStore.getState().snapshot?.document.alignment ?? null;
}

/** The adjustment to start from: the stored one when the alignment of that method is edited. */
export function initialAdjust(method: AlignmentMethod, editTarget: string | null): AlignmentAdjust {
  const alignment = committedAlignment();
  return editTarget === 'alignment' && alignment?.method === method ? alignment.adjust : NO_ADJUST;
}

/** Commit an alignment as one revision (undoable like every document change). */
export async function commitAlignment(
  method: AlignmentMethod,
  params: JsonValue,
  adjust: AlignmentAdjust,
): Promise<void> {
  const baseRevision = currentRevision();
  if (baseRevision === null) return;
  await kernel().call('doc.apply', {
    baseRevision,
    ops: [{ type: 'setAlignment', method, params, adjust }],
    label: 'alignment',
  }).result;
}
