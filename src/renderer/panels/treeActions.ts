// Document edits started from the project tree: rename, suppress and delete.
// Each is one `doc.apply` call, so each is one undo step.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { DocOp } from '@shared/protocol/generated/document-ops';

import { i18n } from '../i18n';
import { KernelFailure } from '../kernel/KernelFailure';
import { describeError } from '../kernel/describeError';
import { kernel } from '../kernel/kernel';
import { currentRevision, documentStore } from '../state/documentStore';
import { exclusiveJobRunning } from '../state/jobStore';
import { showMessage } from '../state/messageStore';
import { selectObjects } from '../state/objectSelectionStore';
import { toolStore } from '../state/toolStore';

export interface TreeDialogState {
  rename: { featureId: string; name: string } | null;
  /** Delete confirmation, shown only when the feature has dependents. */
  remove: { featureId: string; dependents: string[] } | null;
}

export const treeDialogStore = createStore<TreeDialogState>(() => ({ rename: null, remove: null }));

export function useTreeDialogs<T>(selector: (state: TreeDialogState) => T): T {
  return useStore(treeDialogStore, selector);
}

export function closeTreeDialogs(): void {
  treeDialogStore.setState({ rename: null, remove: null });
}

/** Tree edits are blocked while a tool is open or a long job runs (docs/DESIGN.md 5.1, 5.7). */
export function canEditDocument(): boolean {
  return !toolStore.getState().activeToolId && !exclusiveJobRunning();
}

async function apply(ops: DocOp[], label: string): Promise<boolean> {
  const baseRevision = currentRevision();
  if (baseRevision === null) return false;
  try {
    await kernel().call('doc.apply', { baseRevision, ops, label }).result;
    return true;
  } catch (error) {
    if (error instanceof KernelFailure) {
      showMessage('error', describeError(error, i18n.t), error.details);
      return false;
    }
    throw error;
  }
}

function feature(featureId: string) {
  return documentStore.getState().snapshot?.document.features.find((f) => f.id === featureId);
}

export function startRename(featureId: string, displayName: string): void {
  if (!canEditDocument() || !feature(featureId)) return;
  treeDialogStore.setState({ rename: { featureId, name: displayName } });
}

/** An empty name restores the default name ("Zylinder 2"). */
export async function renameFeature(featureId: string, name: string): Promise<boolean> {
  const trimmed = name.trim();
  return apply(
    [{ type: 'renameFeature', id: featureId, name: trimmed === '' ? null : trimmed }],
    i18n.t('panels:undo.rename'),
  );
}

export async function toggleSuppressed(featureId: string): Promise<boolean> {
  const current = feature(featureId);
  if (!current || !canEditDocument()) return false;
  const suppressed = !current.suppressed;
  return apply(
    [{ type: 'setSuppressed', id: featureId, suppressed }],
    i18n.t(suppressed ? 'panels:undo.suppress' : 'panels:undo.unsuppress'),
  );
}

/** Delete at once when nothing depends on the feature, otherwise ask first. */
export async function requestDelete(featureId: string): Promise<void> {
  if (!feature(featureId) || !canEditDocument()) return;
  const { featureIds } = await kernel().call('doc.dependents', { featureId }).result;
  const dependents = featureIds.filter((id) => id !== featureId);
  if (dependents.length) {
    treeDialogStore.setState({ remove: { featureId, dependents } });
    return;
  }
  await deleteFeature(featureId, false);
}

export async function deleteFeature(featureId: string, cascade: boolean): Promise<boolean> {
  const done = await apply(
    [{ type: 'deleteFeature', id: featureId, cascade }],
    i18n.t('panels:undo.delete'),
  );
  if (done) selectObjects([]);
  return done;
}
