import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

interface TreeFilterState {
  /** Hide regions a feature already uses (docs/DESIGN.md 5.5). */
  onlyUnusedRegions: boolean;
}

export const treeFilterStore = createStore<TreeFilterState>(() => ({ onlyUnusedRegions: false }));

export function useTreeFilter<T>(selector: (state: TreeFilterState) => T): T {
  return useStore(treeFilterStore, selector);
}

export function setOnlyUnusedRegions(onlyUnusedRegions: boolean): void {
  treeFilterStore.setState({ onlyUnusedRegions });
}
