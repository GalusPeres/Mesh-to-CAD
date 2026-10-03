import { i18n } from '../i18n';
import { isSilentFailure } from '../kernel/KernelFailure';
import { describeError } from '../kernel/describeError';
import { showMessage } from '../state/messageStore';
import { toFailure } from '../tools/framework/hooks';

/** Show a failed selection or region request in the status bar (cancelled ones stay silent). */
export function reportFailure(error: unknown): void {
  if (isSilentFailure(error)) return;
  showMessage('error', describeError(toFailure(error), i18n.t));
}
