import { useCallback, useEffect, useRef, useState } from 'react';

import type { RecognizeParams, RecognizeResult } from '@shared/protocol/generated/recognize';

import { type KernelFailure, isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { toFailure } from '../framework/hooks';

export const RECOGNIZE_LANE = 'recognize.run:recognize';
/** Started a moment after the parameters rest (React mounts effects twice in development). */
const START_DELAY_MS = 50;

export type Recognition =
  | { status: 'idle' }
  | { status: 'computing'; fraction: number | null; stage: string | null }
  | { status: 'ok'; result: RecognizeResult }
  | { status: 'cancelled' }
  | { status: 'error'; error: KernelFailure };

type Settled = Extract<Recognition, { status: 'ok' | 'cancelled' | 'error' }>;

interface Keyed<T> {
  params: RecognizeParams;
  attempt: number;
  value: T;
}

/**
 * `recognize.run` (an exclusive kernel job) with progress for memoised `params`. A new
 * parameter object starts a new run in the tool's lane, `cancel` stops the running
 * one and `restart` runs the same parameters again.
 */
export function useRecognition(params: RecognizeParams | null): {
  recognition: Recognition;
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
      const job = kernel().call('recognize.run', params, { lane: RECOGNIZE_LANE });
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
    }, START_DELAY_MS);
    return () => {
      current = false;
      clearTimeout(timer);
      running.current?.cancel();
      running.current = null;
    };
  }, [params, attempt]);

  const cancel = useCallback(() => running.current?.cancel(), []);
  const restart = useCallback(() => setAttempt((value) => value + 1), []);

  const matches = (keyed: { params: RecognizeParams; attempt: number } | null | undefined) =>
    params !== null && keyed?.params === params && keyed.attempt === attempt;
  let recognition: Recognition;
  if (params === null) recognition = { status: 'idle' };
  else if (settled && matches(settled)) recognition = settled.value;
  else {
    const active = progress && matches(progress) ? progress.value : null;
    recognition = {
      status: 'computing',
      fraction: active?.fraction ?? null,
      stage: active?.stage ?? null,
    };
  }
  return { recognition, cancel, restart };
}
