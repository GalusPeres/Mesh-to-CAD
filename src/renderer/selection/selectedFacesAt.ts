import { selectedFaces } from './api';

let cached: { scanKey: string; version: number; faces: Uint32Array } | null = null;

/**
 * The selected faces at a selection version (`selectionStore.version`). Strokes
 * change the mask in place, so components key memoised inputs by the version.
 */
export function selectedFacesAt(scanKey: string, version: number): Uint32Array {
  if (cached?.scanKey !== scanKey || cached.version !== version) {
    cached = { scanKey, version, faces: selectedFaces(scanKey) };
  }
  return cached.faces;
}
