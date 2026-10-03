// What the active selection mode is doing right now, for the drawing over the
// viewport (brush ring, lasso path, rectangle) and the status bar hint.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { ScreenPoint } from '../viewport/api';

export interface SmartPreview {
  faces: number;
  kind: string | null;
  rms: number | null;
  tolerance: number;
}

export interface GestureState {
  /** Pointer over the viewport, or null when it is outside. */
  pointer: ScreenPoint | null;
  /** Ctrl is held: the gesture removes from the selection. */
  removing: boolean;
  /** Screen polygon of a running lasso (x, y pairs). */
  lasso: Float32Array | null;
  /** Corners of a running rectangle. */
  rectangle: { from: ScreenPoint; to: ScreenPoint } | null;
  /** Smart select: the surface under the cursor is being computed. */
  smartBusy: boolean;
  smartPreview: SmartPreview | null;
}

const IDLE: GestureState = {
  pointer: null,
  removing: false,
  lasso: null,
  rectangle: null,
  smartBusy: false,
  smartPreview: null,
};

export const gestureStore = createStore<GestureState>(() => IDLE);

export function useGesture<T>(selector: (state: GestureState) => T): T {
  return useStore(gestureStore, selector);
}

export function updateGesture(patch: Partial<GestureState>): void {
  gestureStore.setState(patch);
}

export function resetGesture(): void {
  gestureStore.setState(IDLE, true);
}
