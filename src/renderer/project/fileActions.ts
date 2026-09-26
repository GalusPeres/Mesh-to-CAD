// New, open and save. Paths never reach the renderer: the main process shows the
// file dialog and calls the kernel (`files.run`), the renderer keeps the file name.

import type { Canceled, RawResponse } from '@shared/bridge';
import type { LoadResult, SaveResult } from '@shared/protocol/generated/project';

import { i18n } from '../i18n';
import { KernelFailure, isSilentFailure } from '../kernel/KernelFailure';
import { describeError } from '../kernel/describeError';
import { kernel } from '../kernel/kernel';
import { documentStore } from '../state/documentStore';
import { clearHistory } from '../state/historyStore';
import { showMessage } from '../state/messageStore';
import { closeTool } from '../tools/framework/toolActions';
import {
  currentProjectState,
  markSaved,
  markUntitled,
  projectStore,
  withoutExtension,
} from './projectStore';
import { applyUiState, collectUiState } from './uiState';
import { askToSave } from './unsavedChanges';

const t = (key: string, options?: Record<string, unknown>) => i18n.t(key, options);

let saving: Promise<boolean> | null = null;

/** Save to the project's file (the dialog proposes its name) or ask for one. */
export function saveProject(): Promise<boolean> {
  return saveOnce(projectStore.getState().fileName === null ? 'saveProjectAs' : 'saveProject');
}

export function saveProjectAs(): Promise<boolean> {
  return saveOnce('saveProjectAs');
}

function saveOnce(action: 'saveProject' | 'saveProjectAs'): Promise<boolean> {
  saving ??= save(action).finally(() => {
    saving = null;
  });
  return saving;
}

async function save(action: 'saveProject' | 'saveProjectAs'): Promise<boolean> {
  const snapshot = documentStore.getState().snapshot;
  if (!snapshot?.document.scan) return false;
  const { name } = currentProjectState(snapshot);
  const response = await window.m2c.files.run(
    action,
    { ui: collectUiState() },
    {
      title: t('project:dialogs.saveTitle'),
      filterName: t('project:dialogs.filterName'),
      defaultName: `${name ?? t('common:untitled')}.m2c`,
    },
  );
  const result = resultOf<SaveResult>(response);
  if (!result) return false;
  markSaved(result.fileName, result.revision);
  showMessage('success', t('project:messages.saved', { fileName: result.fileName }));
  return true;
}

/**
 * Ask about unsaved changes before they would be lost. Returns true when the
 * caller may go on (saved, discarded or nothing to lose).
 */
export async function confirmUnsavedChanges(): Promise<boolean> {
  const { name, unsaved } = currentProjectState(documentStore.getState().snapshot);
  if (!unsaved) return true;
  const choice = await askToSave(name ?? t('common:untitled'));
  if (choice === 'cancel') return false;
  return choice === 'discard' || (await saveProject());
}

/** Start an empty project. */
export async function newProject(): Promise<void> {
  if (!(await confirmUnsavedChanges()) || !(await closeTool())) return;
  try {
    await kernel().call('project.new', {}).result;
  } catch (error) {
    reportFailure(error);
    return;
  }
  clearHistory();
  markUntitled();
}

/** Show the open dialog and open the chosen project. */
export async function openProject(): Promise<void> {
  if (!(await confirmUnsavedChanges()) || !(await closeTool())) return;
  const response = await window.m2c.files.run(
    'openProject',
    {},
    { title: t('project:dialogs.openTitle'), filterName: t('project:dialogs.filterName') },
  );
  const result = resultOf<LoadResult>(response);
  if (result) projectOpened(result, { keepHistory: false });
}

/**
 * Make the loaded project current in the renderer. The undo history is cleared
 * unless the project was opened without asking first (dropped onto the window):
 * then undo can still bring back the document it replaced.
 */
export function projectOpened(result: LoadResult, options: { keepHistory: boolean }): void {
  if (!options.keepHistory) clearHistory();
  markSaved(result.fileName, result.revision);
  applyUiState(result.ui);
  void closeTool({ force: true });
  showMessage('info', t('project:messages.opened', { name: withoutExtension(result.fileName) }));
}

function resultOf<T>(response: RawResponse | Canceled): T | null {
  if ('canceled' in response) return null;
  if (!response.ok) {
    reportFailure(new KernelFailure(response.error));
    return null;
  }
  return response.result as T;
}

export function reportFailure(error: unknown): void {
  const failure =
    error instanceof KernelFailure
      ? error
      : new KernelFailure({ code: 'kernel.internal', params: {}, details: String(error) });
  if (isSilentFailure(failure)) return;
  showMessage('error', describeError(failure, i18n.t), failure.details);
}
