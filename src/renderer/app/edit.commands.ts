import { Redo2, Undo2 } from 'lucide-react';

import { KernelFailure } from '../kernel/KernelFailure';
import { kernel } from '../kernel/kernel';
import { exclusiveJobRunning } from '../state/jobStore';
import {
  draftHistoryHandler,
  dropDocumentEntriesBefore,
  entryToRedo,
  entryToUndo,
  markRedone,
  markUndone,
  selectionHistoryHandler,
} from '../state/historyStore';
import { toolStore } from '../state/toolStore';
import type { AppCommand } from './commands/types';

async function moveTo(revision: number): Promise<boolean> {
  try {
    await kernel().call('doc.checkout', { revision }).result;
    return true;
  } catch (error) {
    // Pruned revisions cannot be restored; the history forgets everything before them.
    if (error instanceof KernelFailure && error.code === 'document.revisionGone') {
      dropDocumentEntriesBefore(revision + 1);
      return false;
    }
    throw error;
  }
}

/**
 * Undo order (docs/DESIGN.md 5.1): the open tool's draft first, then selection
 * strokes. Document revisions are never undone behind an open panel tool.
 */
export async function undo(): Promise<void> {
  if (draftHistoryHandler()?.undo()) return;
  const entry = entryToUndo();
  if (!entry) return;
  if (entry.kind === 'selection') {
    selectionHistoryHandler()?.apply(entry.id, entry.scanKey, 'undo');
    markUndone();
    return;
  }
  if (toolStore.getState().activeToolId) return;
  if (await moveTo(entry.from)) markUndone();
}

export async function redo(): Promise<void> {
  if (draftHistoryHandler()?.redo()) return;
  const entry = entryToRedo();
  if (!entry) return;
  if (entry.kind === 'selection') {
    selectionHistoryHandler()?.apply(entry.id, entry.scanKey, 'redo');
    markRedone();
    return;
  }
  if (toolStore.getState().activeToolId) return;
  if (await moveTo(entry.to)) markRedone();
}

export const commands: readonly AppCommand[] = [
  {
    id: 'edit.undo',
    label: 'common:commands.undo',
    icon: Undo2,
    shortcuts: [{ key: 'z', ctrl: true }],
    placement: { menu: 'edit', group: 1, order: 1 },
    isEnabled: () => (!!draftHistoryHandler() || !!entryToUndo()) && !exclusiveJobRunning(),
    run: undo,
  },
  {
    id: 'edit.redo',
    label: 'common:commands.redo',
    icon: Redo2,
    shortcuts: [
      { key: 'y', ctrl: true },
      { key: 'z', ctrl: true, shift: true },
    ],
    placement: { menu: 'edit', group: 1, order: 2 },
    isEnabled: () => (!!draftHistoryHandler() || !!entryToRedo()) && !exclusiveJobRunning(),
    run: redo,
  },
  {
    id: 'app.quit',
    label: 'common:commands.quit',
    placement: { menu: 'file', group: 9, order: 1 },
    run: () => window.close(),
  },
];
