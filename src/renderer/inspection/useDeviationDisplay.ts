import { useEffect } from 'react';

import { documentStore } from '../state/documentStore';
import { viewStore } from '../state/viewStore';
import { useViewport } from '../viewport/api';
import {
  clearDeviationResult,
  deviationStore,
  deviationValues,
  displayRange,
  isDeviationShown,
} from './deviationStore';

/**
 * Keeps the scan colours in line with the deviation map, its display options and the
 * project tolerance. A map of another scan (new import, repair) is dropped.
 */
export function useDeviationDisplay(): void {
  const viewport = useViewport();
  useEffect(() => {
    if (!viewport) return;
    let applied: string | null = null;
    const apply = () => {
      const scan = documentStore.getState().snapshot?.document.scan ?? null;
      const state = deviationStore.getState();
      if (state.summary && state.summary.scanKey !== scan?.key) {
        clearDeviationResult();
        return;
      }
      const values = deviationValues();
      const settings = documentStore.getState().snapshot?.document.settings;
      const range = settings ? displayRange(state, settings.tolerance) : null;
      if (!isDeviationShown() || !values || !settings || range === null) {
        if (applied !== 'off') viewport.scan.setDeviation(null);
        applied = 'off';
        return;
      }
      const key = `${state.version}|${settings.tolerance}|${range}|${state.scheme}`;
      if (key === applied) return;
      viewport.scan.setDeviation(values.values, {
        tolerance: settings.tolerance,
        range,
        scheme: state.scheme,
      });
      applied = key;
    };
    apply();
    const subscriptions = [
      deviationStore.subscribe(apply),
      viewStore.subscribe(apply),
      documentStore.subscribe(apply),
    ];
    return () => subscriptions.forEach((unsubscribe) => unsubscribe());
  }, [viewport]);
}
