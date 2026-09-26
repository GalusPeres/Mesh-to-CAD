import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useStore } from 'zustand';

import type { DocOp } from '@shared/protocol/generated/document-ops';
import type { FeatureStatus } from '@shared/protocol/generated/document-results';

import { angleZeroDirection, inputFrame } from '../../features/reference/geometry';
import { kernel } from '../../kernel/kernel';
import type { ResultOf } from '../../kernel/KernelClient';
import { currentRevision, useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { getViewport, useViewport } from '../../viewport/api';
import { type CommitState, type PreviewState, useCommit, usePreview } from '../framework/hooks';
import { type ReferenceDraft, type SlotName, definitionOf } from './referenceDraft';

export const TOOL_ID = 'reference-geometry';
const ARC_RADIUS_MM = 20;

export type ReferencePreview = PreviewState<ResultOf<'doc.preview'>>;

/**
 * `doc.preview` of the reference feature in the lane `doc.preview:reference-geometry`,
 * its construction drawn with `viewport.setPreviewItems`, and `doc.apply` on OK.
 */
export function useReferencePreview(
  draft: ReferenceDraft,
  editTarget: string | null,
  close: () => void,
): { preview: ReferencePreview; commit: CommitState } {
  const revision = useDocument((state) => state.snapshot?.revision ?? null);
  const ops = useMemo<DocOp[] | null>(() => {
    const definition = definitionOf(draft);
    if (!definition) return null;
    const params = { definition };
    return editTarget
      ? [{ type: 'updateFeature', id: editTarget, params }]
      : [{ type: 'addFeature', feature: { type: 'reference', params } }];
  }, [draft, editTarget]);
  const params = useMemo(
    () => (ops && revision !== null ? { baseRevision: revision, ops } : null),
    [ops, revision],
  );
  const preview = usePreview('doc.preview', params, TOOL_ID);

  useEffect(() => {
    const viewport = getViewport();
    if (!viewport) return;
    if (preview.status === 'ok') viewport.setPreviewItems(TOOL_ID, preview.result.items);
    else if (preview.status !== 'computing') viewport.setPreviewItems(TOOL_ID, []);
  }, [preview]);
  useEffect(() => () => getViewport()?.setPreviewItems(TOOL_ID, []), []);

  const save = useCallback(async () => {
    const baseRevision = currentRevision();
    if (!ops || baseRevision === null) return;
    await kernel().call('doc.apply', { baseRevision, ops, label: 'reference' }).result;
    close();
  }, [ops, close]);
  return { preview, commit: useCommit(save) };
}

/**
 * Inputs picked in the project tree or on construction geometry in the viewport go
 * to the active slot. `accepts` tells whether a feature fits that slot.
 */
export function useInputPicking(
  activeSlot: SlotName | null,
  accepts: (featureId: string) => boolean,
  assign: (slot: SlotName, featureId: string) => void,
): void {
  const selected = useStore(objectSelectionStore, (state) => state.selected[0] ?? null);
  const viewport = useViewport();
  const latest = useRef({ activeSlot, accepts, assign });
  useEffect(() => {
    latest.current = { activeSlot, accepts, assign };
  });

  useEffect(() => {
    const { activeSlot: slot, accepts: fits, assign: set } = latest.current;
    if (slot && selected?.kind === 'feature' && fits(selected.id)) set(slot, selected.id);
  }, [selected]);

  useEffect(() => {
    if (!viewport) return;
    return viewport.addInteraction({
      onPointerDown: (event) => {
        const { activeSlot: slot, accepts: fits, assign: set } = latest.current;
        if (event.button !== 0 || !slot) return false;
        const hit = viewport.pick(event.screen, { kinds: ['item'] });
        if (hit?.kind !== 'item' || !fits(hit.owner)) return false;
        set(slot, hit.owner);
        return true;
      },
    });
  }, [viewport]);
}

/**
 * Drag handles for the value: an arrow along the plane normal for the offset, an
 * arc around the axis for the angle. They are rebuilt when the committed value changes.
 */
export function useValueHandles(
  draft: ReferenceDraft,
  statuses: Readonly<Record<string, FeatureStatus>>,
  onValue: (value: number) => void,
): void {
  const viewport = useViewport();
  const onValueRef = useRef(onValue);
  useEffect(() => {
    onValueRef.current = onValue;
  });
  const input = draft.type === 'offsetPlane' ? draft.inputs.plane : draft.inputs.axis;
  const frame = input ? inputFrame(input, statuses) : null;
  const key = frame ? `${frame.point.join()}|${frame.direction.join()}` : null;

  useEffect(() => {
    if (!viewport || !frame) return;
    const commit = (value: number | readonly number[]) => {
      if (typeof value === 'number') onValueRef.current(value);
    };
    if (draft.type === 'offsetPlane') {
      const handle = viewport.handles.arrow({
        origin: frame.point,
        direction: frame.direction,
        value: draft.distance,
        onCommit: commit,
      });
      return () => handle.dispose();
    }
    if (draft.type === 'planeThroughAxis') {
      const handle = viewport.handles.arc({
        center: frame.point,
        axis: frame.direction,
        reference: angleZeroDirection(frame.direction),
        radius: ARC_RADIUS_MM,
        value: draft.angleDeg,
        onCommit: commit,
      });
      return () => handle.dispose();
    }
    // The frame is identified by `key`; the object itself is new on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewport, key, draft.type, draft.distance, draft.angleDeg]);
}
