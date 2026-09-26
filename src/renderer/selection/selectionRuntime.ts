// Wiring of the selection module into the running app: undo handler, stored
// options, viewport sync and the interaction of the active selection mode.

import { documentStore } from '../state/documentStore';
import { setSelectionMode, toolStore } from '../state/toolStore';
import type { Viewport, ViewportInteraction } from '../viewport/api';
import { resetGesture, updateGesture } from './gestureStore';
import { createBrushMode } from './modes/brushMode';
import { createShapeMode } from './modes/shapeMode';
import { createSmartMode } from './modes/smartMode';
import type { SelectionMode } from './modes/types';
import { currentScan, installSelectionHistory } from './selectionActions';
import { followStoredOptions } from './selectionOptions';
import { selectionStore, switchScan } from './selectionStore';
import { resetPushed, syncViewport } from './viewportSync';

export type SelectionModeId = 'select-brush' | 'select-smart' | 'select-lasso' | 'select-rectangle';

export const SELECTION_MODES: readonly SelectionModeId[] = [
  'select-brush',
  'select-smart',
  'select-lasso',
  'select-rectangle',
];

export function isSelectionModeId(id: string | null): id is SelectionModeId {
  return SELECTION_MODES.includes(id as SelectionModeId);
}

/** Undo handler and stored options; lives as long as the app. */
export function installSelection(): () => void {
  const uninstallHistory = installSelectionHistory();
  const stopOptions = followStoredOptions();
  return () => {
    stopOptions();
    uninstallHistory();
  };
}

/**
 * Keep the viewport's selected and hidden faces equal to the store. The viewport
 * loads a new scan asynchronously, so the push is retried every frame until the
 * viewport shows the selection's scan.
 */
export function startViewportSync(): () => void {
  let frame = 0;
  const run = () => {
    frame = 0;
    if (!documentStore.getState().snapshot?.document.scan) switchScan(null);
    else currentScan();
    if (!syncViewport()) frame = requestAnimationFrame(run);
  };
  const schedule = () => {
    frame ||= requestAnimationFrame(run);
  };
  resetPushed();
  schedule();
  const unsubscribeSelection = selectionStore.subscribe(schedule);
  const unsubscribeDocument = documentStore.subscribe((state, previous) => {
    if (state.snapshot?.document.scan?.key !== previous.snapshot?.document.scan?.key) schedule();
  });
  return () => {
    cancelAnimationFrame(frame);
    unsubscribeSelection();
    unsubscribeDocument();
  };
}

function createMode(viewport: Viewport, id: SelectionModeId): SelectionMode {
  switch (id) {
    case 'select-brush':
      return createBrushMode(viewport);
    case 'select-smart':
      return createSmartMode(viewport);
    case 'select-lasso':
      return createShapeMode(viewport, 'lasso');
    case 'select-rectangle':
      return createShapeMode(viewport, 'rectangle');
  }
}

/**
 * Run a selection mode in the viewport. Esc cancels the running gesture, or
 * leaves the mode when there is none.
 */
export function runSelectionMode(viewport: Viewport, id: SelectionModeId): () => void {
  const mode = createMode(viewport, id);
  const interaction: ViewportInteraction = {
    ...mode.interaction,
    onKeyDown(event) {
      if (event.key === 'Escape' && !event.ctrlKey && !event.altKey) {
        if (mode.busy()) mode.cancel();
        else setSelectionMode(null);
        return true;
      }
      return mode.interaction.onKeyDown?.(event) ?? false;
    },
  };
  const remove = viewport.addInteraction(interaction);
  const onModifier = (event: KeyboardEvent) => {
    if (event.key === 'Control' && !mode.busy())
      updateGesture({ removing: event.type === 'keydown' });
  };
  window.addEventListener('keydown', onModifier);
  window.addEventListener('keyup', onModifier);
  return () => {
    window.removeEventListener('keydown', onModifier);
    window.removeEventListener('keyup', onModifier);
    remove();
    mode.dispose();
    resetGesture();
    viewport.invalidate();
  };
}

/** Leave the selection mode when the scan goes away (the tools need a scan). */
export function leaveModeWithoutScan(): () => void {
  return documentStore.subscribe((state) => {
    if (!state.snapshot?.document.scan && toolStore.getState().selectionMode) {
      if (isSelectionModeId(toolStore.getState().selectionMode)) setSelectionMode(null);
    }
  });
}
