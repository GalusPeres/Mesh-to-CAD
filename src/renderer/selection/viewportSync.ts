// Keeps the viewport's selected and hidden faces equal to the store. Changes
// made through selectionActions update the viewport incrementally and report
// it here; anything else (a new scan, api.replaceSelection, a remembered
// selection coming back) is pushed as a whole mask once the viewport shows the
// scan the selection belongs to.

import { getViewport } from '../viewport/api';
import { selectionStore } from './selectionStore';

interface Pushed {
  scanKey: string | null;
  version: number;
  hiddenVersion: number;
}

let pushed: Pushed = { scanKey: null, version: -1, hiddenVersion: -1 };

/** The viewport already shows this state (it was updated incrementally). */
export function notePushed(scanKey: string, version: number, hiddenVersion: number): void {
  pushed = { scanKey, version, hiddenVersion };
}

/**
 * Push what the viewport is missing. Returns false while the viewport does not
 * show the selection's scan yet (it is still loading); the caller retries.
 */
export function syncViewport(): boolean {
  const viewport = getViewport();
  const { scanKey, mask, version, hidden, hiddenVersion } = selectionStore.getState();
  if (!viewport || !scanKey) return true;
  if (viewport.scan.scanKey !== scanKey) return false;
  const fresh = pushed.scanKey !== scanKey;
  if (fresh || pushed.version !== version) {
    viewport.scan.setSelection(mask ?? new Uint8Array(viewport.scan.faceCount));
  }
  if (fresh || pushed.hiddenVersion !== hiddenVersion) viewport.scan.setHidden(hidden);
  pushed = { scanKey, version, hiddenVersion };
  viewport.invalidate();
  return true;
}

/** Forget what was pushed (a new viewport was mounted). */
export function resetPushed(): void {
  pushed = { scanKey: null, version: -1, hiddenVersion: -1 };
}
