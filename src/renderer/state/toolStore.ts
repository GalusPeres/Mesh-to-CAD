import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

export type StageId = 'prepare' | 'align' | 'model' | 'inspect';

export const STAGES: readonly StageId[] = ['prepare', 'align', 'model', 'inspect'];

export interface ToolState {
  stage: StageId;
  /** The panel tool shown in the properties panel, if any. */
  activeToolId: string | null;
  /** Data the tool was opened with (for example an import report). */
  activation: unknown;
  /** Feature being edited, when the tool was opened from the tree. */
  editTarget: string | null;
  /**
   * The selection mode (brush, smart select, ...). It is independent of the panel
   * tool, so triangles can be selected while a fit or alignment panel is open.
   */
  selectionMode: string | null;
  /** True while the open tool holds changes that would be lost on close. */
  draftDirty: boolean;
}

export const toolStore = createStore<ToolState>(() => ({
  stage: 'prepare',
  activeToolId: null,
  activation: null,
  editTarget: null,
  selectionMode: null,
  draftDirty: false,
}));

export function useTools<T>(selector: (state: ToolState) => T): T {
  return useStore(toolStore, selector);
}

export function setStage(stage: StageId): void {
  toolStore.setState({ stage });
}

export function setSelectionMode(selectionMode: string | null): void {
  toolStore.setState({ selectionMode });
}

export function setDraftDirty(draftDirty: boolean): void {
  toolStore.setState({ draftDirty });
}
