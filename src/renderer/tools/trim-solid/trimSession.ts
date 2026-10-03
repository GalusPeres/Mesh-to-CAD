// What the pointer does in "Zuschneiden", for the status bar (trimSolid.status.tsx).

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/** pick: nothing under the pointer; keep / remove: what a click on the piece does. */
export type TrimHint = 'pick' | 'keep' | 'remove';

const trimSession = createStore<{ hint: TrimHint | null }>(() => ({ hint: null }));

export function useTrimHint(): TrimHint | null {
  return useStore(trimSession, (state) => state.hint);
}

export function setTrimHint(hint: TrimHint | null): void {
  if (trimSession.getState().hint !== hint) trimSession.setState({ hint });
}
