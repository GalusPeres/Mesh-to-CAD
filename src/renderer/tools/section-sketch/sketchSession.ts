// State of the open sketch that the panel shares with its keyboard commands,
// the status bar item and the viewport caption (they live in other modules).

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { ProfileState } from '@shared/protocol/generated/sketch';

/** What a left click in the viewport does in sketch mode. */
export type SketchMode = 'select' | 'corner' | 'line' | 'circle';

export interface SketchSessionState {
  /** Sketch mode (step 2 of the tool) is on. */
  active: boolean;
  mode: SketchMode;
  /** Caption for the viewport, already translated ("Skizze 1 · Ebene XY + 5,000 mm"). */
  caption: string | null;
  profile: ProfileState | null;
}

export interface SketchActions {
  setMode: (mode: SketchMode) => void;
  closeGap: () => void;
  deleteSelected: () => void;
}

const idle: SketchSessionState = { active: false, mode: 'select', caption: null, profile: null };

export const sketchSession = createStore<SketchSessionState>(() => idle);

let actions: SketchActions | null = null;

export function useSketchSession<T>(selector: (state: SketchSessionState) => T): T {
  return useStore(sketchSession, selector);
}

export function enterSketchMode(): void {
  sketchSession.setState({ active: true, mode: 'select' });
}

export function leaveSketchMode(): void {
  actions = null;
  sketchSession.setState(idle);
}

/** The panel keeps its current actions registered while sketch mode is on. */
export function setSketchActions(handlers: SketchActions | null): void {
  actions = handlers;
}

export function sketchActions(): SketchActions | null {
  return actions;
}

export function updateSketchSession(patch: Partial<Omit<SketchSessionState, 'active'>>): void {
  sketchSession.setState(patch);
}
