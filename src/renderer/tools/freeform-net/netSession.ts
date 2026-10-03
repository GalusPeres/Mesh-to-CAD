// What the freeform-net tool tells around the viewport: its mode (caption at the top
// left) and a short hint for what the pointer does right now (status bar). Set by the
// tool, cleared when it closes.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/**
 * start / face / corner: placing a face (first corner, next corner, rectangle's second
 * corner); empty: no net and not placing; point / edge / border / handle: under the
 * pointer; rows: duplicating edges; idle: nothing under the pointer.
 */
export type NetHint =
  'start' | 'face' | 'corner' | 'empty' | 'point' | 'edge' | 'border' | 'handle' | 'rows' | 'idle';

/** Placing a face by four corners, a rectangle by two, or editing the net. */
export type NetMode = 'face' | 'rectangle' | 'edit';

interface NetSessionState {
  mode: NetMode | null;
  hint: NetHint | null;
  /** The corner of a face being placed next (1..4). */
  corner: number;
}

const netSession = createStore<NetSessionState>(() => ({ mode: null, hint: null, corner: 0 }));

export function useNetSession<T>(selector: (state: NetSessionState) => T): T {
  return useStore(netSession, selector);
}

export function setNetHint(hint: NetHint | null, corner = 0): void {
  const current = netSession.getState();
  if (current.hint !== hint || current.corner !== corner) netSession.setState({ hint, corner });
}

export function setNetMode(mode: NetMode | null): void {
  if (netSession.getState().mode !== mode) netSession.setState({ mode });
}
