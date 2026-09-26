import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearHistory,
  entryToUndo,
  recordHistory,
  setDraftHistoryHandler,
  setSelectionHistoryHandler,
} from '../state/historyStore';
import { toolStore } from '../state/toolStore';
import { redo, undo } from './edit.commands';

describe('undo and redo', () => {
  beforeEach(() => {
    clearHistory();
    setDraftHistoryHandler(null);
    setSelectionHistoryHandler(null);
    toolStore.setState({ activeToolId: null });
  });

  it('undoes selection strokes through the selection handler', async () => {
    const apply = vi.fn();
    setSelectionHistoryHandler({ apply });
    recordHistory({ kind: 'selection', id: 7, scanKey: 'scan:a' });

    await undo();
    expect(apply).toHaveBeenLastCalledWith(7, 'scan:a', 'undo');
    expect(entryToUndo()).toBeUndefined();

    await redo();
    expect(apply).toHaveBeenLastCalledWith(7, 'scan:a', 'redo');
  });

  it('asks the open tool draft first', async () => {
    const draft = { undo: vi.fn(() => true), redo: vi.fn(() => true) };
    setDraftHistoryHandler(draft);
    recordHistory({ kind: 'selection', id: 1, scanKey: 'scan:a' });

    await undo();
    expect(draft.undo).toHaveBeenCalledOnce();
    expect(entryToUndo()).toEqual({ kind: 'selection', id: 1, scanKey: 'scan:a' });
  });

  it('never undoes a revision behind an open panel tool', async () => {
    toolStore.setState({ activeToolId: 'extrude' });
    recordHistory({ kind: 'document', from: 3, to: 4 });

    await undo();
    expect(entryToUndo()).toEqual({ kind: 'document', from: 3, to: 4 });
  });
});
