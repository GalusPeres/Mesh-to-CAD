import { useMemo } from 'react';

import type { PreviewDeviationResult } from '@shared/protocol/generated/inspection';

import { type PreviewState, usePreview } from '../tools/framework/hooks';

/**
 * Deviation summary of the body a solid tool previews (ARCHITECTURE.md 4.7): pass the
 * result key of the `doc.preview` result; the request runs in the tool's own lane after
 * the geometry and is dropped when a newer preview arrives.
 */
export function usePreviewDeviation(
  resultKey: string | null,
  toolId: string,
): PreviewState<PreviewDeviationResult> {
  const params = useMemo(() => (resultKey === null ? null : { resultKey }), [resultKey]);
  return usePreview('inspection.previewDeviation', params, toolId);
}
