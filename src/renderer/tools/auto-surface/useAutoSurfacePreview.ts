import { useCallback, useEffect, useRef, useState } from 'react';

import type { PreviewResult } from '@shared/protocol/generated/doc';
import type { PreviewParams } from '@shared/protocol/generated/surfacing';

import { type KernelFailure, isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { getViewport } from '../../viewport/api';
import { toFailure } from '../framework/hooks';

/** Surfacing takes seconds, so a preview starts only once the values rest. */
export const AUTO_SURFACE_PREVIEW_DELAY_MS = 400;
export const AUTO_SURFACE_TOOL_ID = 'auto-surface';
const LANE = `surfacing.preview:${AUTO_SURFACE_TOOL_ID}`;

export type AutoSurfacePreview =
  | { status: 'idle' }
  | { status: 'computing'; fraction: number | null; stage: string | null }
  | { status: 'ok'; result: PreviewResult }
  | { status: 'cancelled' }
  | { status: 'error'; error: KernelFailure };

type Settled = Extract<AutoSurfacePreview, { status: 'ok' | 'cancelled' | 'error' }>;

interface Keyed<T> {
  params: PreviewParams;
  attempt: number;
  value: T;
}

/**
 * `surfacing.preview` (an exclusive kernel job) with progress for memoised `params`.
 * A new parameter object starts a new run in the tool's lane, `cancel` stops the
 * running one and `restart` runs the same parameters again. The previewed surfaces
 * are drawn with `viewport.setPreviewItems` until the tool closes.
 */
export function useAutoSurfacePreview(params: PreviewParams | null): {
  preview: AutoSurfacePreview;
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
      const job = kernel().call('surfacing.preview', params, { lane: LANE });
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
    }, AUTO_SURFACE_PREVIEW_DELAY_MS);
    return () => {
      current = false;
      clearTimeout(timer);
      running.current?.cancel();
      running.current = null;
    };
  }, [params, attempt]);

  const cancel = useCallback(() => running.current?.cancel(), []);
  const restart = useCallback(() => setAttempt((value) => value + 1), []);

  const matches = (keyed: { params: PreviewParams; attempt: number } | null | undefined) =>
    params !== null && keyed?.params === params && keyed.attempt === attempt;
  let preview: AutoSurfacePreview;
  if (params === null) preview = { status: 'idle' };
  else if (settled && matches(settled)) preview = settled.value;
  else {
    const active = progress && matches(progress) ? progress.value : null;
    preview = {
      status: 'computing',
      fraction: active?.fraction ?? null,
      stage: active?.stage ?? null,
    };
  }

  const items = preview.status === 'ok' ? preview.result.items : null;
  useEffect(() => {
    getViewport()?.setPreviewItems(AUTO_SURFACE_TOOL_ID, items ?? []);
  }, [items]);
  useEffect(() => () => getViewport()?.setPreviewItems(AUTO_SURFACE_TOOL_ID, []), []);

  return { preview, cancel, restart };
}
