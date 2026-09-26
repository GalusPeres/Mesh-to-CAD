import { useCallback, useEffect, useRef, useState } from 'react';

import type { SegmentParams, SegmentResult } from '@shared/protocol/generated/regions';

import { type KernelFailure, isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { toFailure } from '../framework/hooks';

/** Segmentation takes seconds, so a preview starts only once the values rest. */
export const SEGMENT_PREVIEW_DELAY_MS = 400;
export const SEGMENT_LANE = 'regions.segment:segment';

export type SegmentPreview =
  | { status: 'idle' }
  | {
      status: 'computing';
      fraction: number | null;
      stage: string | null;
      previous: SegmentResult | null;
    }
  | { status: 'ok'; result: SegmentResult }
  | { status: 'cancelled' }
  | { status: 'error'; error: KernelFailure };

export type PreviewParams = Omit<SegmentParams, 'dryRun'>;

type Settled =
  | { status: 'ok'; result: SegmentResult }
  | { status: 'cancelled' }
  | { status: 'error'; error: KernelFailure };

interface Keyed<T> {
  params: PreviewParams;
  attempt: number;
  value: T;
}

/**
 * Dry-run segmentation with progress. Each new parameter object starts a new
 * run in the tool's lane (the kernel drops the outdated one); `cancel` stops the
 * running one and `restart` runs the same parameters again. `params` must be
 * memoised by the caller.
 */
export function useSegmentPreview(params: PreviewParams | null): {
  preview: SegmentPreview;
  cancel: () => void;
  restart: () => void;
} {
  const [settled, setSettled] = useState<Keyed<Settled> | null>(null);
  const [progress, setProgress] = useState<Keyed<{ fraction: number | null; stage: string }>>();
  const [attempt, setAttempt] = useState(0);
  const running = useRef<{ cancel(): void } | null>(null);

  useEffect(() => {
    if (params === null) return;
    let current = true;
    const timer = setTimeout(() => {
      const job = kernel().call(
        'regions.segment',
        { ...params, dryRun: true },
        { lane: SEGMENT_LANE },
      );
      running.current = job;
      job.onProgress((fraction, stage) => {
        if (current) setProgress({ params, attempt, value: { fraction, stage } });
      });
      job.result
        .then((result) => {
          if (current) setSettled({ params, attempt, value: { status: 'ok', result } });
        })
        .catch((error: unknown) => {
          if (!current) return;
          const value: Settled = isSilentFailure(error)
            ? { status: 'cancelled' }
            : { status: 'error', error: toFailure(error) };
          setSettled({ params, attempt, value });
        })
        .finally(() => {
          if (running.current === job) running.current = null;
        });
    }, SEGMENT_PREVIEW_DELAY_MS);
    return () => {
      current = false;
      clearTimeout(timer);
      running.current?.cancel();
      running.current = null;
    };
  }, [params, attempt]);

  const cancel = useCallback(() => running.current?.cancel(), []);
  const restart = useCallback(() => setAttempt((value) => value + 1), []);

  if (params === null) return { preview: { status: 'idle' }, cancel, restart };
  const matches = (keyed: { params: PreviewParams; attempt: number } | null | undefined) =>
    keyed?.params === params && keyed.attempt === attempt;
  if (settled && matches(settled)) return { preview: settled.value, cancel, restart };
  const active = progress && matches(progress) ? progress.value : null;
  return {
    preview: {
      status: 'computing',
      fraction: active?.fraction ?? null,
      stage: active?.stage ?? null,
      previous: settled?.value.status === 'ok' ? settled.value.result : null,
    },
    cancel,
    restart,
  };
}
