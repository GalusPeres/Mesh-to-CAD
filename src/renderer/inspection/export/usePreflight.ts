import { useEffect, useState } from 'react';

import type { PreflightResult } from '@shared/protocol/generated/export';

import { type KernelFailure, isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { useDocument } from '../../state/documentStore';
import { toFailure } from '../../tools/framework/hooks';

export type PreflightState =
  | { status: 'checking' }
  | { status: 'ok'; result: PreflightResult }
  | { status: 'error'; error: KernelFailure };

type Settled = Exclude<PreflightState, { status: 'checking' }>;

/**
 * The pre-flight check of every body (and the open surfaces STEP can carry), repeated
 * whenever the document changes.
 */
export function usePreflight(): PreflightState {
  const revision = useDocument((state) => state.snapshot?.revision ?? null);
  const hasBodies = useDocument(
    (state) =>
      (state.snapshot?.status.bodies.length ?? 0) > 0 ||
      !!state.snapshot?.document.features.some((feature) => feature.type === 'freeformNet'),
  );
  const [settled, setSettled] = useState<{ revision: number; state: Settled } | null>(null);

  useEffect(() => {
    if (revision === null || !hasBodies) return;
    let current = true;
    const settle = (state: Settled) => {
      if (current) setSettled({ revision, state });
    };
    kernel()
      .call('export.preflight', { bodies: [] })
      .result.then((result) => settle({ status: 'ok', result }))
      .catch((error: unknown) => {
        if (!isSilentFailure(error)) settle({ status: 'error', error: toFailure(error) });
      });
    return () => {
      current = false;
    };
  }, [revision, hasBodies]);

  return settled?.revision === revision ? settled.state : { status: 'checking' };
}
