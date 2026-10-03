// The net's control points as the user sees them: chosen, pinned, hovered, near the
// pointer (only those are drawn on a dense net) and irregular, and their colours.

import type { NetEditorState } from './netState';
import type { NetOverlay } from './NetOverlay';
import { applyPins } from './netPins';

export type ChooseMode = 'replace' | 'add' | 'remove' | 'toggle';

export class NetPoints {
  readonly chosen = new Set<number>();
  /** Points that dragging, Snap to scan, Smooth and Q leave where they are. */
  readonly pinned = new Set<number>();
  private hover: number | null = null;
  /** Control points near the pointer; only these (and marked ones) are drawn. */
  private nearby = new Set<number>();
  /** Inner control points of valence other than 4, always drawn as warnings. */
  private irregular = new Set<number>();

  get irregularCount(): number {
    return this.irregular.size;
  }

  /** Replace, extend or reduce the chosen points. */
  choose(controls: Iterable<number>, mode: ChooseMode): void {
    if (mode === 'replace') this.chosen.clear();
    for (const control of controls) {
      if (mode === 'remove') this.chosen.delete(control);
      else if (mode === 'toggle' && this.chosen.has(control)) this.chosen.delete(control);
      else this.chosen.add(control);
    }
  }

  /** Pin (or release) the chosen points; true if that changed anything. */
  pinChosen(pin: boolean): boolean {
    return applyPins(this.pinned, this.chosen, pin);
  }

  setPinned(pinned: Iterable<number>): void {
    this.pinned.clear();
    for (const control of pinned) this.pinned.add(control);
  }

  /** The hovered point and the points near the pointer; false if nothing changed. */
  setHover(control: number | null, nearby?: Iterable<number>): boolean {
    if (control === this.hover && !nearby) return false;
    this.hover = control;
    if (nearby) this.nearby = new Set(nearby);
    return true;
  }

  /** A new topology with `count` points: forget points past the end and the hover. */
  renumbered(count: number, irregular: readonly number[]): void {
    for (const set of [this.chosen, this.pinned])
      for (const control of [...set]) if (control >= count) set.delete(control);
    this.hover = null;
    this.irregular = new Set(irregular);
  }

  /** The panel's numbers about the points. */
  counts(): Pick<NetEditorState, 'selected' | 'pinned' | 'chosenPinned'> {
    let chosenPinned = 0;
    for (const control of this.chosen) if (this.pinned.has(control)) chosenPinned += 1;
    return { selected: this.chosen.size, pinned: this.pinned.size, chosenPinned };
  }

  paint(overlay: NetOverlay | null): void {
    overlay?.paintPoints({
      chosen: this.chosen,
      pinned: this.pinned,
      hover: this.hover,
      shown: (control) => this.nearby.has(control),
      irregular: this.irregular,
    });
  }
}
