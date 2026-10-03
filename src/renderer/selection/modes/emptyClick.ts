import type { ScreenPoint, Viewport } from '../../viewport/api';
import { clearSelectedFaces } from '../selectionEdits';

/** Pointer travel up to which a press and release count as a click. */
export const CLICK_SLOP_PX = 4;

export function isClick(from: ScreenPoint, to: ScreenPoint): boolean {
  return Math.hypot(to.x - from.x, to.y - from.y) <= CLICK_SLOP_PX;
}

/**
 * A plain click into empty space clears the selection, as in common CAD programs.
 * Ctrl (remove) clicks never clear.
 */
export function clearOnEmptyClick(viewport: Viewport, at: ScreenPoint, ctrl: boolean): boolean {
  if (ctrl || viewport.pick(at, { kinds: ['scan'] })) return false;
  clearSelectedFaces();
  return true;
}
