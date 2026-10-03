// Undo and redo of a tool draft (Ctrl+Z inside the sketch tool, DESIGN.md 5.1).
// The history is an immutable value, so it can live in React state. A derived
// update of the current entry (the kernel's refit of an edit) replaces it
// without adding a step.

export interface DraftHistory<T> {
  readonly entries: readonly T[];
  readonly position: number;
}

export function startHistory<T>(initial: T): DraftHistory<T> {
  return { entries: [initial], position: 0 };
}

export function currentDraft<T>(history: DraftHistory<T>): T {
  return history.entries[history.position] as T;
}

export function canUndo<T>(history: DraftHistory<T>): boolean {
  return history.position > 0;
}

export function canRedo<T>(history: DraftHistory<T>): boolean {
  return history.position < history.entries.length - 1;
}

/** A new user edit becomes the current entry; the redo part is dropped. */
export function pushDraft<T>(history: DraftHistory<T>, next: T): DraftHistory<T> {
  return {
    entries: [...history.entries.slice(0, history.position + 1), next],
    position: history.position + 1,
  };
}

/** Replace the current entry, e.g. with the refit result of the same edit. */
export function replaceDraft<T>(history: DraftHistory<T>, next: T): DraftHistory<T> {
  const entries = [...history.entries];
  entries[history.position] = next;
  return { entries, position: history.position };
}

export function undoDraft<T>(history: DraftHistory<T>): DraftHistory<T> {
  return canUndo(history) ? { ...history, position: history.position - 1 } : history;
}

export function redoDraft<T>(history: DraftHistory<T>): DraftHistory<T> {
  return canRedo(history) ? { ...history, position: history.position + 1 } : history;
}
