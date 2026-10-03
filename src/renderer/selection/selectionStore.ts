import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/**
 * The working selection as one byte per face of the scan with key `scanKey`,
 * and the faces hidden with H / I on that scan. `version` changes with every
 * change of `mask` (strokes change the array in place and bump the version);
 * `hiddenVersion` likewise for `hidden`.
 */
export interface SelectionState {
  scanKey: string | null;
  mask: Uint8Array | null;
  count: number;
  version: number;
  hidden: Uint8Array | null;
  hiddenCount: number;
  hiddenVersion: number;
}

export const selectionStore = createStore<SelectionState>(() => ({
  scanKey: null,
  mask: null,
  count: 0,
  version: 0,
  hidden: null,
  hiddenCount: 0,
  hiddenVersion: 0,
}));

export function useSelectionState<T>(selector: (state: SelectionState) => T): T {
  return useStore(selectionStore, selector);
}

interface Remembered {
  mask: Uint8Array | null;
  count: number;
  hidden: Uint8Array | null;
  hiddenCount: number;
}

/** Selections of recent scans, so undoing a mesh operation brings its selection back. */
const MEMORY_SIZE = 4;
const memory = new Map<string, Remembered>();

/**
 * Make `scanKey` the current scan: the state of the previous scan is remembered
 * and the remembered state of the new one (if any) comes back.
 */
export function switchScan(scanKey: string | null): void {
  const state = selectionStore.getState();
  if (state.scanKey === scanKey) return;
  if (state.scanKey !== null) {
    memory.delete(state.scanKey);
    memory.set(state.scanKey, {
      mask: state.mask,
      count: state.count,
      hidden: state.hidden,
      hiddenCount: state.hiddenCount,
    });
    while (memory.size > MEMORY_SIZE) {
      const oldest = memory.keys().next().value;
      if (oldest === undefined) break;
      memory.delete(oldest);
    }
  }
  const restored = scanKey === null ? undefined : memory.get(scanKey);
  selectionStore.setState({
    scanKey,
    mask: restored?.mask ?? null,
    count: restored?.count ?? 0,
    version: state.version + 1,
    hidden: restored?.hidden ?? null,
    hiddenCount: restored?.hiddenCount ?? 0,
    hiddenVersion: state.hiddenVersion + 1,
  });
}

/** Forget every remembered scan (tests). */
export function resetSelectionMemory(): void {
  memory.clear();
}
