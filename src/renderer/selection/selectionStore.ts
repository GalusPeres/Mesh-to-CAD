import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/**
 * The selection as one byte per face of the scan with key `scanKey`. The mask
 * array is replaced, never mutated, so `version` identifies its state.
 */
export interface SelectionState {
  scanKey: string | null;
  mask: Uint8Array | null;
  count: number;
  version: number;
}

export const selectionStore = createStore<SelectionState>(() => ({
  scanKey: null,
  mask: null,
  count: 0,
  version: 0,
}));

export function useSelectionState<T>(selector: (state: SelectionState) => T): T {
  return useStore(selectionStore, selector);
}
