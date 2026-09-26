// The last deviation map and how it is displayed. The per-vertex values are large
// typed arrays, so they live outside the store; the store holds a version number.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { DeviationResult } from '@shared/protocol/generated/inspection';
import type { DeviationStats, FaceDeviation } from '@shared/protocol/generated/inspection-stats';

import { viewStore } from '../state/viewStore';
import type { DeviationScheme } from '../viewport/palette';
import { type RangeMode, automaticScaleRange, effectiveRange } from './deviationModel';

export interface DeviationSummary {
  /** Document revision the map was computed for; another revision makes it stale. */
  revision: number;
  scanKey: string;
  bodies: string[];
  maxDistance: number;
  stats: DeviationStats;
  faces: FaceDeviation[];
}

export interface DeviationState {
  /** Changes whenever the values change. */
  version: number;
  summary: DeviationSummary | null;
  rangeMode: RangeMode;
  manualRange: number | null;
  scheme: DeviationScheme;
  legendCollapsed: boolean;
}

export interface DeviationValues {
  /** Signed distance per scan vertex, NaN = no data. */
  values: Float32Array;
  /** Mean of each scan face's vertices (the value under the cursor). */
  faceValues: Float32Array;
}

let current: DeviationValues | null = null;

export const deviationStore = createStore<DeviationState>(() => ({
  version: 0,
  summary: null,
  rangeMode: 'auto',
  manualRange: null,
  scheme: 'standard',
  legendCollapsed: false,
}));

export function useDeviation<T>(selector: (state: DeviationState) => T): T {
  return useStore(deviationStore, selector);
}

export function deviationValues(): DeviationValues | null {
  return current;
}

export function setDeviationResult(result: DeviationResult): void {
  current = { values: result.values, faceValues: result.faceValues };
  const { values: _values, faceValues: _faceValues, ...summary } = result;
  deviationStore.setState(({ version }) => ({ version: version + 1, summary }));
}

export function clearDeviationResult(): void {
  current = null;
  deviationStore.setState(({ version }) => ({ version: version + 1, summary: null }));
  setDeviationVisible(false);
}

/** The map is still valid after a change that cannot move scan or bodies (settings). */
export function carryDeviationTo(revision: number): void {
  const { summary } = deviationStore.getState();
  if (summary) deviationStore.setState({ summary: { ...summary, revision } });
}

export function setRangeMode(rangeMode: RangeMode): void {
  deviationStore.setState({ rangeMode });
}

export function setManualRange(manualRange: number | null): void {
  deviationStore.setState({ manualRange });
}

export function setDeviationScheme(scheme: DeviationScheme): void {
  deviationStore.setState({ scheme });
}

export function setLegendCollapsed(legendCollapsed: boolean): void {
  deviationStore.setState({ legendCollapsed });
}

// viewStore owns the flag but has no action for it yet (interface request T7).
export function setDeviationVisible(deviationVisible: boolean): void {
  if (viewStore.getState().deviationVisible !== deviationVisible) {
    viewStore.setState({ deviationVisible });
  }
}

export function isDeviationShown(): boolean {
  const { deviationVisible, displayMode } = viewStore.getState();
  return deviationVisible || displayMode === 'deviation';
}

let automatic: { version: number; tolerance: number; range: number } | null = null;

/** The scale range in use: manual when valid, else automatic (cached per map and tolerance). */
export function displayRange(state: DeviationState, tolerance: number): number | null {
  if (!current) return null;
  if (automatic?.version !== state.version || automatic.tolerance !== tolerance) {
    const range = automaticScaleRange(current.values, tolerance);
    automatic = { version: state.version, tolerance, range };
  }
  return effectiveRange(state.rangeMode, state.manualRange, automatic.range, tolerance);
}
