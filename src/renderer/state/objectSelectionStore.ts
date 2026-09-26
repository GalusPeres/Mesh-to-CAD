import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/** An object of the project: the scan, a region, a feature or a body. */
export interface ObjectRef {
  kind: 'scan' | 'region' | 'feature' | 'body';
  id: string;
}

/**
 * Selected and hovered objects, shared by the project tree, the properties
 * panel and the viewport (which highlights them). Not the triangle selection.
 */
export interface ObjectSelectionState {
  selected: ObjectRef[];
  hovered: ObjectRef | null;
}

export const objectSelectionStore = createStore<ObjectSelectionState>(() => ({
  selected: [],
  hovered: null,
}));

export function useObjectSelection<T>(selector: (state: ObjectSelectionState) => T): T {
  return useStore(objectSelectionStore, selector);
}

export function sameObject(
  a: ObjectRef | null | undefined,
  b: ObjectRef | null | undefined,
): boolean {
  return !!a && !!b && a.kind === b.kind && a.id === b.id;
}

export function selectObjects(selected: ObjectRef[]): void {
  objectSelectionStore.setState({ selected });
}

export function hoverObject(hovered: ObjectRef | null): void {
  if (!sameObject(objectSelectionStore.getState().hovered, hovered)) {
    objectSelectionStore.setState({ hovered });
  }
}
