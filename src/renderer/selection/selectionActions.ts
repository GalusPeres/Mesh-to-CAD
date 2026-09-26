// Every change of the working selection and of the hidden faces goes through
// here: the store and the viewport are updated incrementally, and each stroke
// or command becomes one entry of the undo history (docs/ARCHITECTURE.md 4.9).

import { documentStore } from '../state/documentStore';
import { historyStore, recordHistory, setSelectionHistoryHandler } from '../state/historyStore';
import { getViewport } from '../viewport/api';
import { setFaces } from './faceMask';
import {
  NO_CHANGE,
  type SelectionChange,
  SelectionHistory,
  inverted,
  isEmptyChange,
} from './selectionHistory';
import { selectionStore, switchScan } from './selectionStore';
import { notePushed } from './viewportSync';

const history = new SelectionHistory();

/** The scan the selection refers to: the document's current scan. */
export function currentScan(): { key: string; faceCount: number } | null {
  const scan = documentStore.getState().snapshot?.document.scan;
  if (!scan) return null;
  if (selectionStore.getState().scanKey !== scan.key) switchScan(scan.key);
  return { key: scan.key, faceCount: scan.faceCount };
}

function ownedMask(key: 'mask' | 'hidden', faceCount: number): Uint8Array {
  const existing = selectionStore.getState()[key];
  if (existing && existing.length === faceCount) return existing;
  const created = new Uint8Array(faceCount);
  selectionStore.setState({ [key]: created });
  return created;
}

/**
 * Apply a change as it is and return what actually changed (faces already in
 * the wanted state are left out). Does not touch the undo history.
 */
function apply(change: SelectionChange): SelectionChange {
  const scan = currentScan();
  if (!scan || isEmptyChange(change)) return NO_CHANGE;
  const mask = ownedMask('mask', scan.faceCount);
  const selected = setFaces(mask, change.selected, 1);
  const deselected = setFaces(mask, change.deselected, 0);
  let hidden = new Uint32Array();
  let shown = new Uint32Array();
  if (change.hidden.length || change.shown.length) {
    const hiddenMask = ownedMask('hidden', scan.faceCount);
    hidden = setFaces(hiddenMask, change.hidden, 1);
    shown = setFaces(hiddenMask, change.shown, 0);
  }
  const state = selectionStore.getState();
  const viewport = getViewport();
  const onScreen = viewport?.scan.scanKey === scan.key;
  if (onScreen && selected.length) viewport.scan.updateSelection(selected, true);
  if (onScreen && deselected.length) viewport.scan.updateSelection(deselected, false);
  const hiddenChanged = hidden.length + shown.length > 0;
  if (onScreen && hiddenChanged) viewport.scan.setHidden(state.hidden);
  const version = selected.length + deselected.length ? state.version + 1 : state.version;
  const hiddenVersion = hiddenChanged ? state.hiddenVersion + 1 : state.hiddenVersion;
  selectionStore.setState({
    count: state.count + selected.length - deselected.length,
    version,
    hiddenCount: state.hiddenCount + hidden.length - shown.length,
    hiddenVersion,
  });
  if (onScreen) notePushed(scan.key, version, hiddenVersion);
  viewport?.invalidate();
  return { selected, deselected, hidden, shown };
}

function record(change: SelectionChange, scanKey: string): void {
  if (isEmptyChange(change)) return;
  recordHistory({ kind: 'selection', id: history.add(change), scanKey });
}

/** Apply a change as one undo step. */
export function changeSelection(change: Partial<SelectionChange>): SelectionChange {
  const scan = currentScan();
  if (!scan) return NO_CHANGE;
  const applied = apply({ ...NO_CHANGE, ...change });
  record(applied, scan.key);
  return applied;
}

/** Select (`value` 1) or deselect (0) faces as one undo step. */
export function setSelected(faces: Uint32Array, value: 0 | 1): SelectionChange {
  return changeSelection(value ? { selected: faces } : { deselected: faces });
}

/**
 * A brush stroke: many small changes that become one undo step. Every face
 * changes at most once per stroke, because a stroke either adds or removes.
 */
export class Stroke {
  private readonly changed: Uint32Array[] = [];
  private readonly scanKey: string | null;

  constructor(readonly value: 0 | 1) {
    this.scanKey = currentScan()?.key ?? null;
  }

  add(faces: Uint32Array): void {
    if (!this.scanKey || currentScan()?.key !== this.scanKey) return;
    const applied = apply(this.value ? { ...NO_CHANGE, selected: faces } : { ...NO_CHANGE, deselected: faces });
    const changed = this.value ? applied.selected : applied.deselected;
    if (changed.length) this.changed.push(changed);
  }

  finish(): void {
    if (!this.scanKey || !this.changed.length) return;
    const total = this.changed.reduce((sum, part) => sum + part.length, 0);
    const faces = new Uint32Array(total);
    let offset = 0;
    for (const part of this.changed) {
      faces.set(part, offset);
      offset += part.length;
    }
    this.changed.length = 0;
    const change = this.value
      ? { ...NO_CHANGE, selected: faces }
      : { ...NO_CHANGE, deselected: faces };
    record(change, this.scanKey);
  }
}

/** Undo and redo of selection entries; entries of another scan are skipped. */
export function applyHistoryEntry(id: number, scanKey: string, direction: 'undo' | 'redo'): void {
  const change = history.get(id);
  if (!change || currentScan()?.key !== scanKey) return;
  apply(direction === 'undo' ? inverted(change) : change);
}

/** Registers the undo handler and prunes changes the history dropped; returns the cleanup. */
export function installSelectionHistory(): () => void {
  setSelectionHistoryHandler({ apply: applyHistoryEntry });
  const unsubscribe = historyStore.subscribe((state, previous) => {
    if (state.entries !== previous.entries) history.retain(state.entries);
  });
  return () => {
    unsubscribe();
    setSelectionHistoryHandler(null);
  };
}

/** Selected faces of the current scan (ascending). */
export function selectionMask(): Uint8Array | null {
  const scan = currentScan();
  const mask = selectionStore.getState().mask;
  return scan && mask?.length === scan.faceCount ? mask : null;
}

export function hiddenMask(): Uint8Array | null {
  const scan = currentScan();
  const hidden = selectionStore.getState().hidden;
  return scan && hidden?.length === scan.faceCount ? hidden : null;
}
