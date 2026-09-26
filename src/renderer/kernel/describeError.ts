import type { TFunction } from 'i18next';

import type { KernelFailure } from './KernelFailure';

/** The user-facing message of a kernel failure; the code is the i18n key in `errors`. */
export function describeError(failure: KernelFailure, t: TFunction): string {
  const key = `errors:${failure.code}`;
  const message = t(key, { ...failure.params, defaultValue: '' });
  return message || t('common:unexpectedError');
}
