// What the freeform-net tool tells the status bar: a short hint for what the pointer
// does right now (set by the viewport interaction, cleared when the tool closes).

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/**
 * start / face / corner: placing a face (first corner, next corner, rectangle's second
 * corner); empty: no net and not placing; point / edge / border / handle: under the
 * pointer; rows: duplicating edges; idle: nothing under the pointer.
 */
export type NetHint =
  'start' | 'face' | 'corner' | 'empty' | 'point' | 'edge' | 'border' | 'handle' | 'rows' | 'idle';

interface NetSessionState {
  hint: NetHint | null;
  /** The corner of a face being placed next (1..4). */
  corner: number;
}

const netSession = createStore<NetSessionState>(() => ({ hint: null, corner: 0 }));

export function useNetSession<T>(selector: (state: NetSessionState) => T): T {
  return useStore(netSession, selector);
}

export function setNetHint(hint: NetHint | null, corner = 0): void {
  const current = netSession.getState();
  if (current.hint !== hint || current.corner !== corner) netSession.setState({ hint, corner });
}
