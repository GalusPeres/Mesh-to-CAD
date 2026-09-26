import { useCallback, useEffect, useMemo } from 'react';

import type { MeshEditResult } from '@shared/protocol/generated/mesh';

import type { ParamsOf } from '../../../kernel/KernelClient';
import { kernel } from '../../../kernel/kernel';
import { useDocument } from '../../../state/documentStore';
import { FACE_STATE, getViewport } from '../../../viewport/api';
import { type CommitState, type PreviewState, useCommit, usePreview } from '../../framework/hooks';
import { uniformStates } from './scanEditModel';

export type ScanEditMethod =
  'mesh.repair' | 'mesh.removeSmallParts' | 'mesh.fillHoles' | 'mesh.decimate';

export interface ScanEdit {
  preview: PreviewState<MeshEditResult>;
  /** The last dry-run result; while a new one is computed, the previous one. */
  result: MeshEditResult | null;
  canCommit: boolean;
  commit: CommitState;
}

/**
 * Dry-run preview and commit of a scan preparation step.
 *
 * The step runs with `dryRun` in the tool's lane after every parameter change
 * and after every document change (undo while the panel is open). The faces the
 * step would remove or flip are shown in the fail colour, the faces around holes
 * it would fill in the pass colour. OK runs the step for real and closes the tool.
 */
export function useScanEdit<M extends ScanEditMethod>(
  method: M,
  params: Omit<ParamsOf<M>, 'dryRun'> | null,
  toolId: string,
  close: () => void,
  highlight: 'removed' | 'filled' = 'removed',
): ScanEdit {
  const revision = useDocument((state) => state.snapshot?.revision ?? null);
  const scanKey = useDocument((state) => state.snapshot?.document.scan?.key ?? null);
  const previewParams = useMemo(
    () => (params === null || revision === null ? null : { ...params, dryRun: true }),
    [params, revision],
  );
  const preview = usePreview(method, previewParams, toolId) as PreviewState<MeshEditResult>;
  const result =
    preview.status === 'ok'
      ? preview.result
      : preview.status === 'computing'
        ? preview.previous
        : null;

  useEffect(() => {
    const scan = getViewport()?.scan;
    if (!scan) return;
    const faces = result?.affectedFaces;
    if (faces && faces.length > 0 && scan.scanKey === scanKey) {
      const state = highlight === 'filled' ? FACE_STATE.pass : FACE_STATE.fail;
      scan.setFaceStates(faces, uniformStates(faces.length, state));
    } else {
      scan.setFaceStates(null);
    }
  }, [result, scanKey, highlight]);
  useEffect(() => () => getViewport()?.scan.setFaceStates(null), []);

  const run = useCallback(async () => {
    if (params === null) return;
    await kernel().call(method, { ...params, dryRun: false }).result;
    close();
  }, [method, params, close]);
  const commit = useCommit(run);

  const canCommit = preview.status === 'ok' && preview.result.changed && params !== null;
  return { preview, result, canCommit, commit };
}
