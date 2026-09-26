import { useCallback, useEffect, useMemo } from 'react';

import type { DocOp } from '@shared/protocol/generated/document-ops';
import type { FeatureTypeId } from '@shared/protocol/generated/index';
import type { PreviewDeviationResult } from '@shared/protocol/generated/inspection';

import { usePreviewDeviation } from '../../../inspection/usePreviewDeviation';
import { kernel } from '../../../kernel/kernel';
import { currentRevision, useDocument } from '../../../state/documentStore';
import { getViewport } from '../../../viewport/api';
import { type CommitState, type PreviewState, useCommit, usePreview } from '../../framework/hooks';
import type { ResultOf } from '../../../kernel/KernelClient';
import { previewResultKey } from './model';

export type SolidPreview = PreviewState<ResultOf<'doc.preview'>>;
export type SolidDeviation = PreviewState<PreviewDeviationResult>;

export interface SolidFeature {
  preview: SolidPreview;
  commit: CommitState;
  /** Deviation of the previewed bodies from the scan; idle while there is no body. */
  deviation: SolidDeviation;
  /** True when the last preview of the current parameters produced a usable feature. */
  previewOk: boolean;
}

/**
 * Preview and commit of one solid feature (ARCHITECTURE.md 4.7): `doc.preview` in the
 * lane `doc.preview:<toolId>` 150 ms after the last change, preview items drawn with
 * `viewport.setPreviewItems`, then `inspection.previewDeviation` for the changed bodies
 * in the lane `inspection.previewDeviation:<toolId>`, and `doc.apply` with the same operation on OK.
 * `params` must be memoised; null (invalid input) shows no preview.
 */
export function useSolidFeature(
  toolId: string,
  type: FeatureTypeId,
  editTarget: string | null,
  params: Record<string, unknown> | null,
  close: () => void,
): SolidFeature {
  const revision = useDocument((state) => state.snapshot?.revision ?? null);

  const ops = useMemo<DocOp[] | null>(() => {
    if (params === null) return null;
    return editTarget
      ? [{ type: 'updateFeature', id: editTarget, params }]
      : [{ type: 'addFeature', feature: { type, params } }];
  }, [editTarget, params, type]);

  const previewParams = useMemo(
    () => (ops && revision !== null ? { baseRevision: revision, ops } : null),
    [ops, revision],
  );
  const preview = usePreview('doc.preview', previewParams, toolId);

  useEffect(() => {
    const viewport = getViewport();
    if (!viewport) return;
    if (preview.status === 'ok') viewport.setPreviewItems(toolId, preview.result.items);
    else if (preview.status !== 'computing') viewport.setPreviewItems(toolId, []);
  }, [preview, toolId]);

  useEffect(() => () => getViewport()?.setPreviewItems(toolId, []), [toolId]);

  const apply = useCallback(async () => {
    const baseRevision = currentRevision();
    if (!ops || baseRevision === null) return;
    await kernel().call('doc.apply', { baseRevision, ops, label: type }).result;
    close();
  }, [close, ops, type]);
  const commit = useCommit(apply);

  const state = preview.status === 'ok' ? preview.result.status?.state : undefined;
  const previewOk = state === 'ok' || state === 'warning';
  const resultKey =
    preview.status === 'ok' && previewOk && preview.result.bodies.length > 0
      ? previewResultKey(preview.result)
      : null;
  const deviation = usePreviewDeviation(resultKey, toolId);
  return { preview, commit, deviation, previewOk };
}
