import { useEffect } from 'react';

import type { FreeformPreviewResult } from '@shared/protocol/generated/freeform';

import { getViewport } from '../../viewport/api';

export const PREVIEW_OWNER = 'freeform-patch';

/**
 * Draws the previewed patch and colours the used triangles pass/fail. While a new
 * preview is computed the previous drawing stays; closing the tool removes both.
 */
export function usePatchViewport(
  faces: Uint32Array | null,
  result: FreeformPreviewResult | null,
  computing: boolean,
): void {
  useEffect(() => {
    const viewport = getViewport();
    if (!viewport || computing) return;
    viewport.setPreviewItems(PREVIEW_OWNER, result?.items ?? []);
    if (result && faces && faces.length === result.faceStates.length) {
      viewport.scan.setFaceStates(faces, result.faceStates);
    } else {
      viewport.scan.setFaceStates(null);
    }
  }, [faces, result, computing]);

  useEffect(
    () => () => {
      const viewport = getViewport();
      viewport?.setPreviewItems(PREVIEW_OWNER, []);
      viewport?.scan.setFaceStates(null);
    },
    [],
  );
}
