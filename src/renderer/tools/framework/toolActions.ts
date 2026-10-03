import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import { documentStore } from '../../state/documentStore';
import { setDraftHistoryHandler } from '../../state/historyStore';
import { exclusiveJobRunning } from '../../state/jobStore';
import { setSelectionMode, toolStore } from '../../state/toolStore';
import { toolById } from './registry';
import type { Availability, ToolDefinition } from './types';

/** A pending "discard changes?" question, answered by the dialog in the shell. */
interface DiscardQuestion {
  toolId: string;
  answer(discard: boolean): void;
}

export const discardQuestionStore = createStore<{ question: DiscardQuestion | null }>(() => ({
  question: null,
}));

export function useDiscardQuestion(): DiscardQuestion | null {
  return useStore(discardQuestionStore, (state) => state.question);
}

function askToDiscard(toolId: string): Promise<boolean> {
  return new Promise((resolve) => {
    discardQuestionStore.setState({
      question: {
        toolId,
        answer: (discard) => {
          discardQuestionStore.setState({ question: null });
          resolve(discard);
        },
      },
    });
  });
}

/** Commits the open panel's draft; true if it did (and closed the panel). */
type DraftKeeper = () => Promise<boolean>;
let draftKeeper: DraftKeeper | null = null;

/** The open panel's way to keep its draft when another tool opens (`keepDraftOnLeave`). */
export function setDraftKeeper(keeper: DraftKeeper | null): void {
  draftKeeper = keeper;
}

export function toolAvailability(tool: ToolDefinition): Availability {
  if (tool.status === 'planned') return { enabled: false, reasonKey: 'common:tool.notImplemented' };
  if (exclusiveJobRunning()) return { enabled: false, reasonKey: 'common:status.computing' };
  return tool.availability?.({ snapshot: documentStore.getState().snapshot }) ?? { enabled: true };
}

/**
 * Close the open panel tool. A changed draft is committed first when the tool keeps its
 * drafts, otherwise the user is asked when the tool requires it.
 */
export async function closeTool(options: { force?: boolean } = {}): Promise<boolean> {
  const { activeToolId, draftDirty } = toolStore.getState();
  if (!activeToolId) return true;
  const tool = toolById(activeToolId);
  const keeper = draftKeeper;
  if (!options.force && draftDirty && tool?.keepDraftOnLeave && keeper) {
    draftKeeper = null;
    if (await keeper()) return true;
  }
  if (!options.force && draftDirty && tool?.confirmDiscard && !(await askToDiscard(activeToolId))) {
    return false;
  }
  setDraftHistoryHandler(null);
  toolStore.setState({ activeToolId: null, activation: null, editTarget: null, draftDirty: false });
  return true;
}

/** Activate a tool: toggle a selection mode, run an action or open a panel. */
export async function openTool(
  id: string,
  activation: unknown = null,
  editTarget: string | null = null,
): Promise<void> {
  const tool = toolById(id);
  if (!tool || !toolAvailability(tool).enabled) return;
  if (tool.kind === 'selection') {
    setSelectionMode(toolStore.getState().selectionMode === id ? null : id);
    return;
  }
  if (tool.kind === 'action') {
    await tool.run?.();
    return;
  }
  const { activeToolId } = toolStore.getState();
  if (activeToolId && activeToolId !== id && !(await closeTool())) return;
  toolStore.setState({ activeToolId: id, activation, editTarget, draftDirty: false });
}
