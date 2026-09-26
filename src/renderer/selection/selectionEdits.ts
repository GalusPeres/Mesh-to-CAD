// Selection commands (Ctrl+A, Ctrl+D, Ctrl+Shift+I, G, Shift+G, H, Shift+H, I).
// Each one is a single undo step of the current scan.

import { getViewport } from '../viewport/api';
import { facesOf, innerRing, outerRing, unselectedVisible } from './faceMask';
import { changeSelection, currentScan, hiddenMask, selectionMask } from './selectionActions';

function emptyMask(): Uint8Array {
  return new Uint8Array(currentScan()?.faceCount ?? 0);
}

export function hasSelection(): boolean {
  const mask = selectionMask();
  return !!mask && mask.includes(1);
}

export function hasHidden(): boolean {
  const hidden = hiddenMask();
  return !!hidden && hidden.includes(1);
}

export function selectAllVisible(): void {
  if (!currentScan()) return;
  changeSelection({ selected: unselectedVisible(selectionMask() ?? emptyMask(), hiddenMask()) });
}

export function clearSelectedFaces(): void {
  const mask = selectionMask();
  if (mask) changeSelection({ deselected: facesOf(mask) });
}

/** Visible faces swap their state; hidden faces stay as they are. */
export function invertSelection(): void {
  if (!currentScan()) return;
  const mask = selectionMask() ?? emptyMask();
  const hidden = hiddenMask();
  const selected = facesOf(mask).filter((face) => !hidden?.[face]);
  changeSelection({ selected: unselectedVisible(mask, hidden), deselected: selected });
}

async function neighbours(): Promise<Int32Array | null> {
  const scan = currentScan();
  const viewport = getViewport();
  if (!scan || !viewport || viewport.scan.scanKey !== scan.key) return null;
  const topology = await viewport.scanTopology();
  // The scan may have changed while the topology was built.
  if (currentScan()?.key !== scan.key || topology.neighbours.length !== scan.faceCount * 3) {
    return null;
  }
  return topology.neighbours;
}

/** G: add the ring of faces around the selection. */
export async function growSelection(): Promise<void> {
  const adjacency = await neighbours();
  const mask = selectionMask();
  if (!adjacency || !mask) return;
  changeSelection({ selected: outerRing(mask, adjacency, hiddenMask()) });
}

/** Shift+G: remove the outermost ring of the selection. */
export async function shrinkSelection(): Promise<void> {
  const adjacency = await neighbours();
  const mask = selectionMask();
  if (!adjacency || !mask) return;
  changeSelection({ deselected: innerRing(mask, adjacency) });
}

/** H: hide the selected faces (they leave the selection). */
export function hideSelection(): void {
  const mask = selectionMask();
  if (!mask) return;
  const faces = facesOf(mask);
  changeSelection({ hidden: faces, deselected: faces });
}

/** Shift+H: show every hidden face again. */
export function showAllFaces(): void {
  const hidden = hiddenMask();
  if (hidden) changeSelection({ shown: facesOf(hidden) });
}

/** I: hide everything that is not selected. */
export function isolateSelection(): void {
  const mask = selectionMask();
  if (!mask || !mask.includes(1)) return;
  changeSelection({ hidden: unselectedVisible(mask, hiddenMask()) });
}
