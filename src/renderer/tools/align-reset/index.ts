import { RotateCcw } from 'lucide-react';

import { i18n } from '../../i18n';
import { KernelFailure } from '../../kernel/KernelFailure';
import { describeError } from '../../kernel/describeError';
import { showMessage } from '../../state/messageStore';
import { NO_ADJUST } from '../align-auto/adjust';
import { commitAlignment } from '../align-auto/alignmentActions';
import type { ToolDefinition } from '../framework/types';

/** Back to scan coordinates (method none, no adjustment); undoable like every commit. */
async function resetAlignment(): Promise<void> {
  try {
    await commitAlignment('none', null, NO_ADJUST);
  } catch (error) {
    if (error instanceof KernelFailure) {
      showMessage('error', describeError(error, i18n.t), error.details);
    } else {
      throw error;
    }
  }
}

export const tool: ToolDefinition = {
  id: 'align-reset',
  kind: 'action',
  status: 'ready',
  stages: ['align'],
  group: 'align',
  icon: RotateCcw,
  availability: ({ snapshot }) => {
    const alignment = snapshot?.document.alignment;
    const aligned =
      !!alignment &&
      (alignment.method !== 'none' ||
        alignment.adjust.flipX ||
        alignment.adjust.flipZ ||
        alignment.adjust.rotateZ90 % 4 !== 0);
    return aligned
      ? { enabled: true }
      : { enabled: false, reasonKey: 'tools:alignReset.notAligned' };
  },
  run: resetAlignment,
};
