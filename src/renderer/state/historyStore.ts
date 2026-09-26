import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/**
 * One linear undo history for document revisions and selection strokes.
 * Selection entries carry only an id; the selection module keeps the face
 * differences itself, keyed by that id.
 */
export type HistoryEntry =
  | { kind: 'document'; from: number; to: number }
  | { kind: 'selection'; id: number; scanKey: string };

export interface HistoryState {
  entries: HistoryEntry[];
  /** Number of entries currently applied; entries after it can be redone. */
  position: number;
}

export const historyStore = createStore<HistoryState>(() => ({ entries: [], position: 0 }));

export function useHistory<T>(selector: (state: HistoryState) => T): T {
  return useStore(historyStore, selector);
}

/** Add an entry after the current position; the redo part is discarded. */
export function recordHistory(entry: HistoryEntry): void {
  historyStore.setState(({ entries, position }) => ({
    entries: [...entries.slice(0, position), entry],
    position: position + 1,
  }));
}

export function entryToUndo(
  state: HistoryState = historyStore.getState(),
): HistoryEntry | undefined {
  return state.entries[state.position - 1];
}

export function entryToRedo(
  state: HistoryState = historyStore.getState(),
): HistoryEntry | undefined {
  return state.entries[state.position];
}

export function markUndone(): void {
  historyStore.setState(({ position }) => ({ position: Math.max(0, position - 1) }));
}

export function markRedone(): void {
  historyStore.setState(({ entries, position }) => ({
    position: Math.min(entries.length, position + 1),
  }));
}

/** Remove entries that point at revisions the kernel no longer keeps. */
export function dropDocumentEntriesBefore(revision: number): void {
  historyStore.setState(({ entries, position }) => {
    const firstKept = entries.findIndex(
      (entry) => entry.kind !== 'document' || entry.from >= revision,
    );
    const cut = firstKept === -1 ? entries.length : firstKept;
    return { entries: entries.slice(cut), position: Math.max(0, position - cut) };
  });
}

export function clearHistory(): void {
  historyStore.setState({ entries: [], position: 0 });
}

/** Applies selection entries; registered by the selection module, which keeps the face diffs. */
export interface SelectionHistoryHandler {
  /** Undo or redo entry `id`. Entries of another scan (`scanKey`) are skipped as no-ops. */
  apply(id: number, scanKey: string, direction: 'undo' | 'redo'): void;
}

/** Undo steps inside an open tool (its draft); registered while the tool is open. */
export interface DraftHistoryHandler {
  /** Returns false when the draft has nothing (more) to undo or redo. */
  undo(): boolean;
  redo(): boolean;
}

let selectionHandler: SelectionHistoryHandler | null = null;
let draftHandler: DraftHistoryHandler | null = null;

export function setSelectionHistoryHandler(handler: SelectionHistoryHandler | null): void {
  selectionHandler = handler;
}

export function selectionHistoryHandler(): SelectionHistoryHandler | null {
  return selectionHandler;
}

/** Tools call this when they open with a draft history and pass null when they close. */
export function setDraftHistoryHandler(handler: DraftHistoryHandler | null): void {
  draftHandler = handler;
}

export function draftHistoryHandler(): DraftHistoryHandler | null {
  return draftHandler;
}
