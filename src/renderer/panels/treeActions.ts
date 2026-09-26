// Document edits started from the project tree: rename, suppress and delete.
// Each is one `doc.apply` call, so each is one undo step.

import type { TFunction } from 'i18next';
import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { DocOp } from '@shared/protocol/generated/document-ops';

import type { Formatter } from '../i18n/format';
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
  /** Delete confirmation, shown only when other features use the one to delete. */
  remove: { featureId: string; dependents: string[] } | null;
}

export const treeDialogStore = createStore<TreeDialogState>(() => ({ rename: null, remove: null }));

export function useTreeDialogs<T>(selector: (state: TreeDialogState) => T): T {
  return useStore(treeDialogStore, selector);
}

export function closeTreeDialogs(): void {
  treeDialogStore.setState({ rename: null, remove: null });
}

/** Tree edits wait while a tool is open or a long job runs (docs/DESIGN.md 5.1, 5.7). */
export function canEditDocument(): boolean {
  return !toolStore.getState().activeToolId && !exclusiveJobRunning();
}

/**
 * Like `canEditDocument`, but says why an edit from the tree (delete, suppress,
 * rename) cannot run instead of ignoring the key press silently.
 */
export function editableOrExplain(): boolean {
  if (canEditDocument()) return true;
  const key = toolStore.getState().activeToolId ? 'panels:blocked.toolOpen' : 'panels:blocked.busy';
  showMessage('info', i18n.t(key));
  return false;
}

function reportFailure(error: unknown): void {
  if (!(error instanceof KernelFailure)) throw error;
  showMessage('error', describeError(error, i18n.t), error.details);
}

async function apply(ops: DocOp[], label: string): Promise<boolean> {
  const baseRevision = currentRevision();
  if (baseRevision === null) return false;
  try {
    await kernel().call('doc.apply', { baseRevision, ops, label }).result;
    return true;
  } catch (error) {
    reportFailure(error);
    return false;
  }
}

function findFeature(featureId: string) {
  return documentStore.getState().snapshot?.document.features.find((f) => f.id === featureId);
}

export function startRename(featureId: string, displayName: string): void {
  if (!findFeature(featureId) || !editableOrExplain()) return;
  treeDialogStore.setState({ rename: { featureId, name: displayName } });
}

/** An empty name restores the default name ("Zylinder 2"). */
export async function renameFeature(featureId: string, name: string): Promise<boolean> {
  const trimmed = name.trim();
  const current = findFeature(featureId);
  if (!current || (current.name ?? '') === trimmed) return false;
  return apply(
    [{ type: 'renameFeature', id: featureId, name: trimmed === '' ? null : trimmed }],
    i18n.t('panels:undo.rename'),
  );
}

export async function toggleSuppressed(featureId: string): Promise<boolean> {
  const current = findFeature(featureId);
  if (!current || !editableOrExplain()) return false;
  const suppressed = !current.suppressed;
  return apply(
    [{ type: 'setSuppressed', id: featureId, suppressed }],
    i18n.t(suppressed ? 'panels:undo.suppress' : 'panels:undo.unsuppress'),
  );
}

/** Delete at once when nothing uses the feature, otherwise ask first. */
export async function requestDelete(featureId: string): Promise<void> {
  if (!findFeature(featureId) || !editableOrExplain()) return;
  let dependents: string[];
  try {
    const { featureIds } = await kernel().call('doc.dependents', { featureId }).result;
    dependents = featureIds.filter((id) => id !== featureId);
  } catch (error) {
    reportFailure(error);
    return;
  }
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

/** "Skizze 1 wird von Extrusion 1 und Verrundung 1 verwendet. Alle 3 löschen?" */
export function dependentsQuestion(
  featureId: string,
  dependents: readonly string[],
  names: ReadonlyMap<string, string>,
  format: Formatter,
  t: TFunction,
): string {
  const name = (id: string) => names.get(id) ?? id;
  return t('panels:delete.withDependents', {
    name: name(featureId),
    dependents: format.list(dependents.map(name)),
    count: dependents.length + 1,
  });
}
