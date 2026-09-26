import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearHistory,
  dropDocumentEntriesBefore,
  entryToRedo,
  entryToUndo,
  historyStore,
  markRedone,
  markUndone,
  recordHistory,
} from './historyStore';

describe('history', () => {
  beforeEach(clearHistory);

  it('undoes and redoes in order', () => {
    recordHistory({ kind: 'document', from: 0, to: 1 });
    recordHistory({ kind: 'document', from: 1, to: 2 });
    expect(entryToUndo()).toEqual({ kind: 'document', from: 1, to: 2 });
    markUndone();
    expect(entryToUndo()).toEqual({ kind: 'document', from: 0, to: 1 });
    expect(entryToRedo()).toEqual({ kind: 'document', from: 1, to: 2 });
    markRedone();
    expect(entryToRedo()).toBeUndefined();
  });

  it('drops the redo part when something new is recorded', () => {
    recordHistory({ kind: 'document', from: 0, to: 1 });
    recordHistory({ kind: 'document', from: 1, to: 2 });
    markUndone();
    recordHistory({ kind: 'document', from: 1, to: 3 });
    expect(historyStore.getState().entries).toHaveLength(2);
    expect(entryToRedo()).toBeUndefined();
  });

  it('forgets entries that point at revisions the kernel pruned', () => {
    recordHistory({ kind: 'document', from: 0, to: 1 });
    recordHistory({ kind: 'document', from: 1, to: 2 });
    recordHistory({ kind: 'document', from: 2, to: 3 });
    dropDocumentEntriesBefore(2);
    expect(historyStore.getState()).toEqual({
      entries: [{ kind: 'document', from: 2, to: 3 }],
      position: 1,
    });
  });
});
