import { useEffect, useRef } from 'react';

import type { PieceChoice } from '@shared/protocol/generated/feature-trim-solid';

import { setToolInfoProvider } from '../../automation/toolInfo';
import type { SolidPreview } from '../extrude/solid/useSolidFeature';
import type { TrimInputs } from './inputs';

interface TrimState {
  inputs: TrimInputs;
  pieces: readonly PieceChoice[];
  preview: SolidPreview;
  canCommit: boolean;
}

/**
 * What "Zuschneiden" tells automation clients (docs/AUTOMATION.md, `toolInfo`): the
 * inputs, the clicked pieces and the preview's result, so an assistant can check it.
 */
export function useTrimAutomation(state: TrimState): void {
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });
  useEffect(
    () =>
      setToolInfoProvider(() => {
        const { inputs, pieces, preview, canCommit } = latest.current;
        const result = preview.status === 'ok' ? preview.result : null;
        return {
          tool: 'trim-solid',
          inputs,
          pieces,
          preview: preview.status,
          state: result?.status?.state ?? null,
          error: result?.status?.error?.code ?? (preview.status === 'error' ? 'kernel' : null),
          stats: result?.status?.stats ?? null,
          volume: result?.bodies[0]?.volume ?? null,
          canCommit,
        };
      }),
    [],
  );
}
