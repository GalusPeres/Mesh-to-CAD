import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import type { DocOp } from '@shared/protocol/generated/document-ops';

import { featureNames } from '../../features/registry';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { selectedFaces } from '../../selection/api';
import { useSelectionState } from '../../selection/selectionStore';
import { currentRevision, useDocument } from '../../state/documentStore';
import { setDraftDirty } from '../../state/toolStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { SCENE_COLORS } from '../../viewport/palette';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from './FreeformNetPanel.module.css';
import { FREEFORM_NET_TOOL_ID } from './netEditor';
import type { BoxRectangle } from './netInteraction';
import {
  DENSITY_QUADS,
  DeviationSection,
  EditSection,
  ErrorMessage,
  GenerateSection,
  type NetDensity,
  type NetSource,
  ResultSection,
} from './NetSections';
import { useNetEditor, useNetState } from './useNetEditor';

/** The selected triangles, recomputed whenever the selection changes. */
function useSelectionFaces(): Uint32Array {
  const scanKey = useDocument((state) => state.snapshot?.document.scan?.key ?? null);
  const version = useSelectionState((state) => state.version);
  return useMemo(
    () => selectedFaces(scanKey),
    // `version` changes whenever the selection does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scanKey, version],
  );
}

/**
 * Freiform-Netz: a clean quad net is laid over the scan (or the selected triangles)
 * and snapped to it; its control points can be dragged while the surface and its
 * deviation from the scan update live. OK turns the net into B-spline CAD faces.
 */
export function FreeformNetPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const { editor, box } = useNetEditor(editTarget);
  const state = useNetState(editor);
  const features = useDocument((snapshot) => snapshot.snapshot?.document.features);
  const [source, setSource] = useState<NetSource>('scan');
  const [density, setDensity] = useState<NetDensity>('medium');
  const selection = useSelectionFaces();

  const generate = useCallback(() => {
    if (!editor) return;
    const faces = source === 'selection' ? selection.slice() : null;
    void editor.generate(faces, DENSITY_QUADS[density]);
  }, [editor, source, selection, density]);

  const apply = useCallback(async () => {
    const net = editor?.current();
    const baseRevision = currentRevision();
    if (!editor || !net || baseRevision === null) return;
    const params: Record<string, unknown> = {
      vertices: net.vertices,
      quads: net.quads,
      faces: editor.faces,
    };
    const ops: DocOp[] = editTarget
      ? [{ type: 'updateFeature', id: editTarget, params }]
      : [{ type: 'addFeature', feature: { type: 'freeformNet', params } }];
    await kernel().call('doc.apply', { baseRevision, ops, label: 'freeformNet' }).result;
    close();
  }, [editor, editTarget, close]);
  const commit = useCommit(apply);

  // A new net, or a change to an edited one, is a draft worth asking about before discarding.
  const dirty = !!state && (editTarget ? state.canUndo : state.hasNet);
  useEffect(() => {
    if (dirty) setDraftDirty(true);
  }, [dirty]);

  const names = useMemo(() => featureNames(features ?? [], t), [features, t]);
  const canCommit = !!state?.hasNet && state.job === null && !editor?.dragging;

  return (
    <ToolPanel
      toolId={FREEFORM_NET_TOOL_ID}
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={canCommit}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      {editor && state && (
        <>
          <GenerateSection
            editor={editor}
            state={state}
            source={source}
            density={density}
            selectionCount={selection.length}
            onSource={setSource}
            onDensity={setDensity}
            onGenerate={generate}
          />
          <ErrorMessage state={state} />
          {state.hasNet && (
            <>
              <EditSection editor={editor} state={state} />
              <DeviationSection editor={editor} state={state} />
              <ResultSection state={state} />
            </>
          )}
        </>
      )}
      {commit.error && (
        <InlineMessage severity="error" details={commit.error.details}>
          {describeError(commit.error, t)}
        </InlineMessage>
      )}
      <BoxSelection box={box} />
    </ToolPanel>
  );
}

/** The rectangle of a box selection, drawn over the viewport. */
function BoxSelection({ box }: { box: BoxRectangle | null }) {
  // The viewport area; the rectangle is drawn over it like the selection gestures.
  const [host] = useState<HTMLElement | null>(() => document.querySelector('main'));
  if (!host || !box) return null;
  const x = Math.min(box.from.x, box.to.x);
  const y = Math.min(box.from.y, box.to.y);
  const width = Math.abs(box.to.x - box.from.x);
  const height = Math.abs(box.to.y - box.from.y);
  return createPortal(
    <svg className={styles.drawing} aria-hidden data-testid="freeform-net-box">
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill="none"
        stroke={SCENE_COLORS.brushDark}
        strokeWidth={3}
      />
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill="none"
        stroke={SCENE_COLORS.brushLight}
      />
    </svg>,
    host,
  );
}
