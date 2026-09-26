// The working selection of scan triangles, as other modules see it. Tools read the
// selected faces from here; only the selection module changes them.

import { selectionStore, useSelectionState } from './selectionStore';

/** Indices of the selected faces, ascending. Empty when the selection belongs to an older scan. */
export function selectedFaces(scanKey: string | null): Uint32Array {
  const { mask, scanKey: owner } = selectionStore.getState();
  if (!mask || owner !== scanKey) return new Uint32Array();
  const faces: number[] = [];
  mask.forEach((value, face) => {
    if (value) faces.push(face);
  });
  return Uint32Array.from(faces);
}

export function useSelectedFaceCount(): number {
  return useSelectionState((state) => state.count);
}

/** Replace the selection (used when a tool loads the stored faces of a feature it edits). */
export function replaceSelection(scanKey: string, faceCount: number, faces: Uint32Array): void {
  const mask = new Uint8Array(faceCount);
  for (const face of faces) mask[face] = 1;
  selectionStore.setState({
    scanKey,
    mask,
    count: faces.length,
    version: selectionStore.getState().version + 1,
  });
}

export function clearSelection(): void {
  selectionStore.setState(({ version }) => ({ mask: null, count: 0, version: version + 1 }));
}
