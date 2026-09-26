// Smart select (W): resting the cursor on the scan for 300 ms grows the surface
// under it in the kernel (regions.grow) and shows it as the hover tint. A click
// adds it, Ctrl + click removes it, Ctrl + wheel changes the tolerance. Requests
// run in one lane, so moving on drops outdated ones.

import { kernel } from '../../kernel/kernel';
import type { ScreenPoint, Viewport, ViewportInteraction } from '../../viewport/api';
import { updateGesture } from '../gestureStore';
import { reportFailure } from '../reportFailure';
import { currentScan, setSelected, withoutHidden } from '../selectionActions';
import {
  SMART_TOLERANCE,
  type SmartMode,
  selectionOptionsStore,
  setSelectionOptions,
} from '../selectionOptions';
import type { SelectionMode } from './types';

export const SMART_DWELL_MS = 300;
export const SMART_LANE = 'regions.grow:select-smart';
/** A press that moves farther than this is a camera drag, not a click. */
const CLICK_SLOP_PX = 4;
/** Ctrl + wheel changes the tolerance by this factor per notch. */
const TOLERANCE_STEP = 1.25;

interface Grown {
  scanKey: string;
  mode: SmartMode;
  tolerance: number | null;
  faces: Uint32Array;
  /** Membership of `faces`: is the cursor still on the shown surface? */
  member: Set<number>;
}

/** Tolerance one Ctrl + wheel notch away from `base`, rounded to three digits. */
export function steppedTolerance(base: number, up: boolean): number {
  const next = Number((base * (up ? TOLERANCE_STEP : 1 / TOLERANCE_STEP)).toPrecision(3));
  return Math.min(SMART_TOLERANCE.max, Math.max(SMART_TOLERANCE.min, next));
}

export function createSmartMode(viewport: Viewport): SelectionMode {
  let dwell: ReturnType<typeof setTimeout> | undefined;
  let hoverFace: number | null = null;
  let grown: Grown | null = null;
  let request: { seed: number; promise: Promise<Grown | null> } | null = null;
  let press: { at: ScreenPoint; ctrl: boolean } | null = null;
  /** The distance limit the kernel used last (the automatic one when none is set). */
  let usedTolerance: number | null = null;
  let disposed = false;
  let lastMove: ScreenPoint | null = null;
  let frame = 0;

  const faceAt = (at: ScreenPoint): number | null => {
    const hit = viewport.pick(at, { kinds: ['scan'] });
    return hit?.kind === 'scan' ? hit.face : null;
  };

  const clearPreview = () => {
    if (grown) viewport.scan.setHover(null);
    grown = null;
    updateGesture({ smartPreview: null });
  };

  const grow = (seed: number): Promise<Grown | null> => {
    const scan = currentScan();
    if (!scan) return Promise.resolve(null);
    const { smartMode: mode, smartTolerance: tolerance } = selectionOptionsStore.getState();
    updateGesture({ smartBusy: true });
    const promise: Promise<Grown | null> = kernel()
      .call(
        'regions.grow',
        { scanKey: scan.key, seedFace: seed, mode, tolerance },
        { lane: SMART_LANE },
      )
      .result.then((result) => {
        const faces = withoutHidden(result.faces);
        const next: Grown = { scanKey: scan.key, mode, tolerance, faces, member: new Set(faces) };
        usedTolerance = result.tolerance;
        if (!disposed && request?.promise === promise) {
          request = null;
          grown = next;
          viewport.scan.setHover(faces);
          updateGesture({
            smartBusy: false,
            smartPreview: {
              faces: faces.length,
              kind: result.kind,
              rms: result.rms,
              tolerance: result.tolerance,
            },
          });
        }
        return next;
      })
      .catch((error: unknown) => {
        if (request?.promise === promise) {
          request = null;
          updateGesture({ smartBusy: false });
        }
        reportFailure(error);
        return null;
      });
    request = { seed, promise };
    return promise;
  };

  /** The shown surface, if it still contains `face` and matches the options. */
  const shownFor = (face: number | null): Grown | null => {
    const { smartMode, smartTolerance } = selectionOptionsStore.getState();
    const valid =
      grown !== null &&
      face !== null &&
      grown.scanKey === currentScan()?.key &&
      grown.mode === smartMode &&
      grown.tolerance === smartTolerance &&
      grown.member.has(face);
    return valid ? grown : null;
  };

  const hover = (face: number | null, delay = SMART_DWELL_MS) => {
    clearTimeout(dwell);
    hoverFace = face;
    if (face !== null && shownFor(face)) return;
    clearPreview();
    if (face !== null) dwell = setTimeout(() => void grow(face), delay);
  };

  const commit = async (at: ScreenPoint, remove: boolean) => {
    const face = faceAt(at);
    if (face === null) return;
    clearTimeout(dwell);
    const result =
      shownFor(face) ?? (await (request?.seed === face ? request.promise : grow(face)));
    if (result && !disposed) setSelected(result.faces, remove ? 0 : 1);
  };

  /** One pick per animation frame; a new face under the cursor restarts the dwell. */
  const pickHover = () => {
    frame = 0;
    if (!lastMove || disposed) return;
    const face = faceAt(lastMove);
    if (face !== hoverFace || (face !== null && !shownFor(face) && !request)) hover(face);
  };

  const interaction: ViewportInteraction = {
    cursor: 'crosshair',
    onPointerDown(event) {
      if (event.button !== 0 || event.alt) return false;
      press = { at: event.screen, ctrl: event.ctrl };
      return true;
    },
    onPointerMove(event) {
      updateGesture({ pointer: event.screen, removing: event.ctrl });
      if (event.buttons !== 0) return false;
      lastMove = event.screen;
      frame ||= requestAnimationFrame(pickHover);
      return false;
    },
    onPointerUp(event) {
      const started = press;
      press = null;
      if (!started) return false;
      const moved = Math.hypot(event.screen.x - started.at.x, event.screen.y - started.at.y);
      if (moved <= CLICK_SLOP_PX) void commit(event.screen, started.ctrl || event.ctrl);
      return true;
    },
    onWheel(event) {
      if (!event.ctrl) return false;
      const base = selectionOptionsStore.getState().smartTolerance ?? usedTolerance;
      if (base === null) return true;
      setSelectionOptions({ smartTolerance: steppedTolerance(base, event.deltaY < 0) });
      if (hoverFace !== null) hover(hoverFace, SMART_DWELL_MS / 3);
      return true;
    },
  };

  // A changed mode or tolerance in the options bar recomputes the surface under the cursor.
  const unsubscribe = selectionOptionsStore.subscribe((state, previous) => {
    const changed =
      state.smartMode !== previous.smartMode || state.smartTolerance !== previous.smartTolerance;
    if (changed && hoverFace !== null) hover(hoverFace, SMART_DWELL_MS / 3);
  });

  return {
    interaction,
    busy: () => press !== null,
    cancel: () => {
      press = null;
    },
    dispose: () => {
      clearTimeout(dwell);
      cancelAnimationFrame(frame);
      unsubscribe();
      clearPreview();
      disposed = true;
      request = null;
      updateGesture({ smartBusy: false, smartPreview: null });
    },
  };
}
