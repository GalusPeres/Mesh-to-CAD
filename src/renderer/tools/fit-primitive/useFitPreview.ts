import { useEffect, useMemo, useState } from 'react';

import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';

import type { KernelFailure } from '../../kernel/KernelFailure';
import { isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import type { ResultOf } from '../../kernel/KernelClient';
import {
  clearSelection,
  replaceSelection,
  selectedFaces,
  useSelectedFaceCount,
} from '../../selection/api';
import { useDocument } from '../../state/documentStore';
import { getViewport } from '../../viewport/api';
import { type PreviewState, toFailure, usePreview } from '../framework/hooks';
import { type FitDraft, previewParams } from './fitDraft';

export const TOOL_ID = 'fit-primitive';

export interface FitInput {
  faces: Uint32Array;
  scanKey: string | null;
  faceCount: number;
  /** False while an edited fit's triangles are still loading into the selection. */
  ready: boolean;
  loadError: KernelFailure | null;
}

/**
 * The working selection as the fit's input. When a fit is edited, its stored
 * triangles become the selection, and the previous selection returns when the
 * tool closes (docs/DESIGN.md 5.1).
 */
export function useFitInput(editTarget: string | null): FitInput {
  const scanKey = useDocument((state) => state.snapshot?.document.scan?.key ?? null);
  const faceCount = useDocument((state) => state.snapshot?.document.scan?.faceCount ?? 0);
  const count = useSelectedFaceCount();
  const [ready, setReady] = useState(editTarget === null);
  const [loadError, setLoadError] = useState<KernelFailure | null>(null);

  useEffect(() => {
    if (!editTarget || !scanKey) return;
    const previous = selectedFaces(scanKey);
    let current = true;
    kernel()
      .call('fit.featureFaces', { featureId: editTarget })
      .result.then((stored) => {
        if (!current) return;
        replaceSelection(stored.scanKey, faceCount, stored.faces);
        setReady(true);
      })
      .catch((error: unknown) => {
        if (current && !isSilentFailure(error)) setLoadError(toFailure(error));
      });
    return () => {
      current = false;
      if (previous.length > 0) replaceSelection(scanKey, faceCount, previous);
      else clearSelection();
    };
  }, [editTarget, scanKey, faceCount]);

  const faces = useMemo(
    () => selectedFaces(scanKey),
    // The selection API signals changes through the count; read the faces again then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [count, scanKey],
  );
  return { faces, scanKey, faceCount, ready, loadError };
}

export type FitPreview = PreviewState<ResultOf<'fit.preview'>>;

/**
 * `fit.preview` in the tool's lane 150 ms after the last change, with pass/fail
 * colouring of the used triangles and the construction preview in the viewport.
 */
export function useFitPreview(draft: FitDraft, input: FitInput): FitPreview {
  const { faces, scanKey, ready } = input;
  const params = useMemo(
    () =>
      ready && scanKey && faces.length >= MIN_FIT_FACES
        ? previewParams(draft, faces, scanKey)
        : null,
    [draft, faces, scanKey, ready],
  );
  const preview = usePreview('fit.preview', params, TOOL_ID);

  useEffect(() => {
    const viewport = getViewport();
    if (!viewport) return;
    if (preview.status === 'ok' && params) {
      viewport.scan.setFaceStates(params.faces, preview.result.faceStates);
      viewport.setPreviewItems(TOOL_ID, preview.result.items);
    } else if (preview.status !== 'computing') {
      viewport.scan.setFaceStates(null);
      viewport.setPreviewItems(TOOL_ID, []);
    }
  }, [preview, params]);

  useEffect(
    () => () => {
      const viewport = getViewport();
      viewport?.scan.setFaceStates(null);
      viewport?.setPreviewItems(TOOL_ID, []);
    },
    [],
  );
  return preview;
}
