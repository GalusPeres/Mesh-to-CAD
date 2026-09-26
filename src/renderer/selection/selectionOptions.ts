// Options of the selection modes (brush size, Nur sichtbare, Durch das Teil,
// smart-select tolerance). They are remembered in the per-tool preferences.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { JsonValue } from '@shared/protocol/wireTypes';

import { settingsStore, updateSettings } from '../state/settingsStore';

export type SmartMode = 'primitive' | 'smooth';

export interface SelectionOptions {
  /** Brush radius in CSS pixels. */
  brushRadius: number;
  /** Brush and smart select: only faces facing the camera and not covered. */
  visibleOnly: boolean;
  /** Lasso and rectangle: select through the part (also covered faces). */
  throughPart: boolean;
  smartMode: SmartMode;
  /** Distance limit of smart select in mm; null = from the scan noise. */
  smartTolerance: number | null;
}

export const BRUSH_RADIUS = { min: 4, max: 200, default: 24 } as const;
export const SMART_TOLERANCE = { min: 0.001, max: 10 } as const;

const DEFAULTS: SelectionOptions = {
  brushRadius: BRUSH_RADIUS.default,
  visibleOnly: true,
  throughPart: false,
  smartMode: 'primitive',
  smartTolerance: null,
};

/** Key of the per-tool preferences that hold these options. */
const SETTINGS_KEY = 'selection';

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Options from stored preferences; anything invalid falls back to the default. */
export function optionsFromSettings(stored: JsonValue | undefined): SelectionOptions {
  const data =
    typeof stored === 'object' && stored !== null && !Array.isArray(stored) ? stored : {};
  const radius = data.brushRadius;
  const tolerance = data.smartTolerance;
  return {
    brushRadius:
      typeof radius === 'number' && Number.isFinite(radius)
        ? clamp(Math.round(radius), BRUSH_RADIUS.min, BRUSH_RADIUS.max)
        : DEFAULTS.brushRadius,
    visibleOnly: typeof data.visibleOnly === 'boolean' ? data.visibleOnly : DEFAULTS.visibleOnly,
    throughPart: typeof data.throughPart === 'boolean' ? data.throughPart : DEFAULTS.throughPart,
    smartMode: data.smartMode === 'smooth' ? 'smooth' : 'primitive',
    smartTolerance:
      typeof tolerance === 'number' && Number.isFinite(tolerance)
        ? clamp(tolerance, SMART_TOLERANCE.min, SMART_TOLERANCE.max)
        : null,
  };
}

export const selectionOptionsStore = createStore<SelectionOptions>(() =>
  optionsFromSettings(settingsStore.getState().tools[SETTINGS_KEY]),
);

export function useSelectionOptions<T>(selector: (options: SelectionOptions) => T): T {
  return useStore(selectionOptionsStore, selector);
}

let saveTimer: ReturnType<typeof setTimeout> | undefined;

function save(): void {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const { brushRadius, visibleOnly, throughPart, smartMode, smartTolerance } =
      selectionOptionsStore.getState();
    const value = { brushRadius, visibleOnly, throughPart, smartMode, smartTolerance };
    // Without the preload bridge (unit tests) the options simply are not remembered.
    if (typeof window === 'undefined' || !('m2c' in window)) return;
    updateSettings({ tools: { [SETTINGS_KEY]: value } }).catch(() => undefined);
  }, 500);
}

export function setSelectionOptions(patch: Partial<SelectionOptions>): void {
  selectionOptionsStore.setState(patch);
  save();
}

/** Grow or shrink the brush by one step (`[`, `]`, Ctrl + wheel): 15 % per step. */
export function resizeBrush(steps: number): void {
  const current = selectionOptionsStore.getState().brushRadius;
  const next = clamp(Math.round(current * 1.15 ** steps), BRUSH_RADIUS.min, BRUSH_RADIUS.max);
  if (next === current && steps !== 0) {
    const nudged = clamp(current + Math.sign(steps), BRUSH_RADIUS.min, BRUSH_RADIUS.max);
    setSelectionOptions({ brushRadius: nudged });
    return;
  }
  setSelectionOptions({ brushRadius: next });
}

/** Load the stored options once the preferences arrived from the main process. */
export function followStoredOptions(): () => void {
  return settingsStore.subscribe((state, previous) => {
    if (state.tools[SETTINGS_KEY] !== previous.tools[SETTINGS_KEY]) {
      selectionOptionsStore.setState(optionsFromSettings(state.tools[SETTINGS_KEY]));
    }
  });
}
