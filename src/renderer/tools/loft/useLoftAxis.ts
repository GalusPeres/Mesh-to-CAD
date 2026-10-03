import { useEffect, useRef, useState } from 'react';

import type { LoftAxisResult } from '@shared/protocol/generated/freeform';

import { isSilentFailure, type KernelFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { getViewport } from '../../viewport/api';
import { toFailure } from '../framework/hooks';

export type LoftAxisState =
  | { status: 'loading' }
  | { status: 'ok'; axis: LoftAxisResult }
  | { status: 'error'; error: KernelFailure };

/** The loft axis in part coordinates and the scan's extent along it (for defaults and handles). */
export function useLoftAxis(
  path: string,
  faces: Uint32Array | null,
  revision: number | null,
): LoftAxisState {
  const [state, setState] = useState<{ key: string; value: LoftAxisState } | null>(null);
  const key = `${path}:${revision ?? ''}:${faces?.length ?? 'all'}`;
  useEffect(() => {
    if (revision === null) return;
    let current = true;
    kernel()
      .call('freeform.loftAxis', { path, faces })
      .result.then((axis) => {
        if (current) setState({ key, value: { status: 'ok', axis } });
      })
      .catch((error: unknown) => {
        if (current && !isSilentFailure(error)) {
          setState({ key, value: { status: 'error', error: toFailure(error) } });
        }
      });
    return () => {
      current = false;
    };
  }, [key, path, faces, revision]);
  return state?.key === key ? state.value : { status: 'loading' };
}

interface RangeHandleOptions {
  axis: LoftAxisResult | null;
  start: number;
  end: number;
  /** Changes when start or end were typed, so the handles move there. */
  revision: number;
  onStart: (value: number) => void;
  onEnd: (value: number) => void;
}

/** Arrow handles along the axis for the first and the last section. */
export function useRangeHandles({
  axis,
  start,
  end,
  revision,
  onStart,
  onEnd,
}: RangeHandleOptions): void {
  const latest = useRef({ start, end, onStart, onEnd });
  useEffect(() => {
    latest.current = { start, end, onStart, onEnd };
  });
  const axisKey = axis
    ? [...axis.point, ...axis.direction].map((value) => value.toFixed(4)).join(',')
    : null;

  useEffect(() => {
    const viewport = getViewport();
    if (!viewport || !axis || axisKey === null) return;
    const handles = (['start', 'end'] as const).map((which) =>
      viewport.handles.arrow({
        origin: axis.point,
        direction: axis.direction,
        value: latest.current[which],
        color: 'axis',
        onChange: (value) => {
          if (typeof value !== 'number') return;
          if (which === 'start') latest.current.onStart(value);
          else latest.current.onEnd(value);
        },
        onCommit: (value) => {
          if (typeof value !== 'number') return;
          if (which === 'start') latest.current.onStart(value);
          else latest.current.onEnd(value);
        },
      }),
    );
    return () => handles.forEach((handle) => handle.dispose());
    // `axisKey` stands for the axis; the handles are rebuilt when a value is typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [axisKey, revision]);
}
