import { useCallback, useEffect, useState } from 'react';

import type { MethodName } from '@shared/protocol/generated/index';

import { KernelFailure, isSilentFailure } from '../../kernel/KernelFailure';
import type { ParamsOf, ResultOf } from '../../kernel/KernelClient';
import { kernel } from '../../kernel/kernel';

export const PREVIEW_DEBOUNCE_MS = 150;

export type PreviewState<T> =
  | { status: 'idle' }
  | { status: 'computing'; previous: T | null }
  | { status: 'ok'; result: T }
  | { status: 'error'; error: KernelFailure };

interface Settled<P, T> {
  params: P;
  state: { status: 'ok'; result: T } | { status: 'error'; error: KernelFailure };
}

/**
 * Recompute a preview 150 ms after the last parameter change. Requests go to the
 * tool's own lane (`<method>:<toolId>`), so the kernel drops outdated ones, and
 * answers to outdated parameters are ignored here. Pass `null` to disable.
 * `params` must be memoised by the caller: every new object starts a preview.
 */
export function usePreview<M extends MethodName>(
  method: M,
  params: ParamsOf<M> | null,
  toolId: string,
): PreviewState<ResultOf<M>> {
  const [settled, setSettled] = useState<Settled<ParamsOf<M>, ResultOf<M>> | null>(null);

  useEffect(() => {
    if (params === null) return;
    let current = true;
    const timer = setTimeout(() => {
      kernel()
        .call(method, params, { lane: `${method}:${toolId}` })
        .result.then((result) => {
          if (current) setSettled({ params, state: { status: 'ok', result } });
        })
        .catch((error: unknown) => {
          if (current && !isSilentFailure(error)) {
            setSettled({ params, state: { status: 'error', error: toFailure(error) } });
          }
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [method, params, toolId]);

  if (params === null) return { status: 'idle' };
  if (settled?.params !== params) {
    return {
      status: 'computing',
      previous: settled?.state.status === 'ok' ? settled.state.result : null,
    };
  }
  return settled.state;
}

export interface CommitState {
  commit: () => Promise<boolean>;
  busy: boolean;
  error: KernelFailure | null;
}

/** Wraps a tool's commit: tracks the running request and keeps its error for the panel. */
export function useCommit(handler: () => Promise<void>): CommitState {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<KernelFailure | null>(null);
  const commit = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await handler();
      return true;
    } catch (failure) {
      if (!isSilentFailure(failure)) setError(toFailure(failure));
      return false;
    } finally {
      setBusy(false);
    }
  }, [handler]);
  return { commit, busy, error };
}

export function toFailure(error: unknown): KernelFailure {
  if (error instanceof KernelFailure) return error;
  const details = error instanceof Error ? (error.stack ?? error.message) : String(error);
  return new KernelFailure({ code: 'kernel.internal', params: {}, details });
}
