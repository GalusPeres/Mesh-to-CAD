import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';

import { isSelectionModeId } from '../../selection/selectionRuntime';
import { useDocument } from '../../state/documentStore';
import { setDraftHistoryHandler } from '../../state/historyStore';
import { toolStore } from '../../state/toolStore';
import { useViewport } from '../../viewport/api';
import { NetEditor, type NetEditorState } from './netEditor';
import { type BoxRectangle, createNetInteraction } from './netInteraction';

/**
 * The tool's NetEditor for as long as the panel is open: it owns the viewport
 * overlay and pointer handling, answers Ctrl+Z inside the tool, and hides the
 * edited feature's own body while its net is being changed.
 */
export function useNetEditor(editTarget: string | null): {
  editor: NetEditor | null;
  box: BoxRectangle | null;
} {
  const viewport = useViewport();
  const tolerance = useDocument((state) => state.snapshot?.document.settings.tolerance ?? 0.1);
  const [box, setBox] = useState<BoxRectangle | null>(null);
  // One editor per viewport; its tolerance at creation, later changes are passed on below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const editor = useMemo(() => (viewport ? new NetEditor(viewport, tolerance) : null), [viewport]);

  useEffect(() => {
    if (!viewport || !editor) return;
    editor.attach();
    const removeInteraction = viewport.addInteraction(
      createNetInteraction(editor, viewport, {
        onBox: setBox,
        selectionModeActive: () => isSelectionModeId(toolStore.getState().selectionMode),
      }),
    );
    setDraftHistoryHandler({ undo: () => editor.undo(), redo: () => editor.redo() });
    if (editTarget) {
      viewport.setOwnerHidden(editTarget);
      if (!editor.getState().hasNet) void editor.load(editTarget);
    }
    return () => {
      removeInteraction();
      setDraftHistoryHandler(null);
      viewport.setOwnerHidden(null);
      editor.detach();
    };
  }, [viewport, editor, editTarget]);

  useEffect(() => editor?.setTolerance(tolerance), [editor, tolerance]);
  return { editor, box };
}

const EMPTY: NetEditorState | null = null;

/** The editor's numbers for the panel; null while there is no editor. */
export function useNetState(editor: NetEditor | null): NetEditorState | null {
  return useSyncExternalStore(
    editor ? editor.subscribe : noSubscription,
    editor ? editor.getState : () => EMPTY,
  );
}

function noSubscription(): () => void {
  return () => undefined;
}
