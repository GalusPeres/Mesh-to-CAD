// @vitest-environment happy-dom

import { act } from 'react';
import { type Root, createRoot } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { DeviationResult } from '@shared/protocol/generated/inspection';

import { i18n, initI18n, setLanguage } from '../i18n';
import { setDocumentSnapshot } from '../state/documentStore';
import { setDisplayMode } from '../state/viewStore';
import { TooltipProvider } from '../ui/Tooltip/Tooltip';
import { DeviationLegend } from './DeviationLegend';
import { statusItem } from './deviation.status';
import {
  clearDeviationResult,
  setDeviationResult,
  setDeviationScheme,
  setDeviationVisible,
} from './deviationStore';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function snapshot(revision: number): DocumentSnapshot {
  return {
    revision,
    cause: 'commit',
    label: 'test',
    document: {
      scan: { key: 'scan:a', vertexCount: 4, faceCount: 2, noise: 0.03 },
      settings: {
        tolerance: 0.1,
        snapUnits: 'metric',
        noiseOverride: null,
        deviationMaxDistance: 2,
      },
      features: [],
    },
    status: { features: {}, bodies: [] },
  } as unknown as DocumentSnapshot;
}

function result(): DeviationResult {
  return {
    revision: 5,
    scanKey: 'scan:a',
    bodies: ['f1'],
    maxDistance: 2,
    values: new Float32Array([0.01, -0.02, 0.4, Number.NaN]),
    faceValues: new Float32Array([0.0, 0.13]),
    stats: {
      count: 3,
      tolerance: 0.1,
      mean: 0.003,
      std: 0.046,
      rms: 0.046,
      min: -0.28,
      max: 0.372,
      p05: -0.03,
      p50: 0,
      p95: 0.03,
      p99Abs: 0.3,
      within: 0.977,
      above: 0.015,
      below: 0.008,
      passed: true,
      histogramCounts: [],
      histogramLimit: 0.3,
    },
    faces: [],
  };
}

describe('deviation legend', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeAll(async () => {
    await initI18n('de');
  });

  beforeEach(() => {
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    setDisplayMode('shaded');
    setDocumentSnapshot(snapshot(5));
    setDeviationResult(result());
    setDeviationScheme('standard');
  });

  afterEach(async () => {
    act(() => root.unmount());
    container.remove();
    clearDeviationResult();
    setDocumentSnapshot(null);
    await setLanguage('de');
  });

  const Status = statusItem.Component;
  const render = () =>
    act(() =>
      root.render(
        <TooltipProvider>
          <DeviationLegend />
          <Status />
        </TooltipProvider>,
      ),
    );

  it('is hidden until the display is switched on', () => {
    setDeviationVisible(false);
    render();
    expect(container.textContent).toBe('');
  });

  it('shows ticks, tolerance bracket, swatches and statistics', () => {
    setDeviationVisible(true);
    render();
    const text = container.textContent ?? '';
    for (const tick of ['+0,50', '+0,33', '+0,17', '+0,10', '−0,10', '−0,33', '−0,50']) {
      expect(text).toContain(tick);
    }
    expect(text).toContain('Toleranz ±0,10');
    expect(text).toContain('außerhalb');
    expect(text).toContain('keine Daten');
    expect(text).toContain('+0,003');
    expect(text).toContain('97,7 % in Toleranz');
    expect(text).toContain('Max +0,372 / −0,280');
    expect(text).toContain('Abweichung: 97,7 % in Toleranz');
    expect(text).not.toContain('Stand vor der letzten Änderung');
  });

  it('says when the map is older than the document, in English too', async () => {
    setDeviationVisible(true);
    setDocumentSnapshot(snapshot(6));
    await setLanguage('en');
    render();
    const text = container.textContent ?? '';
    expect(text).toContain('Deviation [mm]');
    expect(text).toContain('+0.50');
    expect(text).toContain('Before the last change');
    expect(i18n.language).toBe('en');
  });
});
