// Undo information of selection changes. The shared history (state/historyStore)
// holds only `{ kind: 'selection', id, scanKey }`; the faces that changed are
// kept here, per entry id.

import type { HistoryEntry } from '../state/historyStore';

/** Faces whose selected or hidden state a stroke or command changed. */
export interface SelectionChange {
  selected: Uint32Array;
  deselected: Uint32Array;
  hidden: Uint32Array;
  shown: Uint32Array;
}

export const NO_CHANGE: SelectionChange = {
  selected: new Uint32Array(),
  deselected: new Uint32Array(),
  hidden: new Uint32Array(),
  shown: new Uint32Array(),
};

export function isEmptyChange(change: SelectionChange): boolean {
  return (
    change.selected.length + change.deselected.length + change.hidden.length + change.shown.length ===
    0
  );
}

/** The change that undoes `change`. */
export function inverted(change: SelectionChange): SelectionChange {
  return {
    selected: change.deselected,
    deselected: change.selected,
    hidden: change.shown,
    shown: change.hidden,
  };
}

export class SelectionHistory {
  private nextId = 1;
  private readonly changes = new Map<number, SelectionChange>();

  /** Store a change and return the id for its history entry. */
  add(change: SelectionChange): number {
    const id = this.nextId;
    this.nextId += 1;
    this.changes.set(id, change);
    return id;
  }

  get(id: number): SelectionChange | undefined {
    return this.changes.get(id);
  }

  /** Drop the changes of entries the shared history no longer has (redo cut off). */
  retain(entries: readonly HistoryEntry[]): void {
    const alive = new Set(
      entries.flatMap((entry) => (entry.kind === 'selection' ? [entry.id] : [])),
    );
    for (const id of this.changes.keys()) if (!alive.has(id)) this.changes.delete(id);
  }

  get size(): number {
    return this.changes.size;
  }
}
