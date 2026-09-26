import type { KernelErrorPayload } from '@shared/bridge';

/** A failed kernel request. `code` is also the i18n key in the `errors` namespace. */
export class KernelFailure extends Error {
  override name = 'KernelFailure';
  readonly code: string;
  readonly params: Record<string, unknown>;
  readonly details?: string;

  constructor(payload: KernelErrorPayload) {
    super(payload.code);
    this.code = payload.code;
    this.params = payload.params ?? {};
    this.details = payload.details;
  }
}

const SILENT_CODES = new Set(['kernel.cancelled', 'kernel.superseded', 'kernel.busy']);

/** Cancelled, superseded and busy requests are expected and never shown to the user. */
export function isSilentFailure(error: unknown): boolean {
  return error instanceof KernelFailure && SILENT_CODES.has(error.code);
}
