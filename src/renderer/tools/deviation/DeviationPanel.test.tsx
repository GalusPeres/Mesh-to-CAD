// @vitest-environment happy-dom

import { act } from 'react';
import { type Root, createRoot } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { DeviationResult } from '@shared/protocol/generated/inspection';

import { initI18n } from '../../i18n';
import {
  clearDeviationResult,
  deviationStore,
  deviationValues,
} from '../../inspection/deviationStore';
import { setDocumentSnapshot } from '../../state/documentStore';
import { viewStore } from '../../state/viewStore';
import { TooltipProvider } from '../../ui/Tooltip/Tooltip';
import { DeviationPanel } from './DeviationPanel';

const calls: { method: string; params: unknown; lane?: string }[] = [];

function deviation(within: number): DeviationResult {
  return {
    revision: 3,
    scanKey: 'scan:a',
    bodies: ['f5'],
    maxDistance: 2,
    values: new Float32Array([0.01, -0.02, Number.NaN]),
    faceValues: new Float32Array([0]),
    stats: {
      count: 2,
      tolerance: 0.1,
      mean: 0.003,
      std: 0.046,
      rms: 0.046,
      min: -0.28,
      max: 0.372,
      p05: null,
      p50: null,
      p95: null,
      p99Abs: 0.3,
      within,
      above: 0,
      below: 0,
      passed: within >= 0.95,
      histogramCounts: [],
      histogramLimit: 0.3,
    },
    faces: [],
  };
}

let within = 0.977;

vi.mock('../../kernel/kernel', () => ({
  kernel: () => ({
    call: (method: string, params: unknown, options: { lane?: string } = {}) => {
      calls.push({ method, params, lane: options.lane });
      return { result: Promise.resolve(deviation(within)) };
    },
  }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function snapshot(): DocumentSnapshot {
  return {
    revision: 3,
    cause: 'commit',
    label: 'test',
    document: {
      scan: { key: 'scan:a', vertexCount: 3, faceCount: 1, noise: 0.036 },
      settings: {
        tolerance: 0.1,
        snapUnits: 'metric',
        noiseOverride: null,
        deviationMaxDistance: 2,
      },
      features: [],
    },
    status: { features: {}, bodies: [{ id: 'f5', owner: 'f5' }] },
  } as unknown as DocumentSnapshot;
}

describe('deviation panel', () => {
  let container: HTMLDivElement;
  let root: Root;
  const close = vi.fn();

  beforeAll(async () => {
    await initI18n('de');
  });

  beforeEach(() => {
    calls.length = 0;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    setDocumentSnapshot(snapshot());
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    clearDeviationResult();
    setDocumentSnapshot(null);
    close.mockReset();
  });

  const wait = (ms: number) => act(async () => new Promise((resolve) => setTimeout(resolve, ms)));
  const render = () =>
    act(() =>
      root.render(
        <TooltipProvider>
          <DeviationPanel activation={null} editTarget={null} close={close} />
        </TooltipProvider>,
      ),
    );

  it('computes the map on opening, shows the statistics and keeps the display on', async () => {
    within = 0.977;
    render();
    expect(viewStore.getState().deviationVisible).toBe(true);
    await wait(200);

    expect(calls).toEqual([
      {
        method: 'inspection.deviation',
        params: { bodies: ['f5'], maxDistance: 2 },
        lane: 'inspection.deviation:deviation',
      },
    ]);
    expect(deviationValues()?.values).toHaveLength(3);
    expect(deviationStore.getState().summary?.bodies).toEqual(['f5']);
    const text = container.querySelector('[data-testid="deviation-result"]')?.textContent ?? '';
    expect(text).toContain('Scanrauschen0,036 mm');
    expect(text).toContain('Mittelwert+0,003 mm');
    expect(text).toContain('In Toleranz97,7 %');
    expect(text).toContain('Ohne Daten1');

    await act(async () =>
      (container.querySelector('[data-testid="panel-ok"]') as HTMLButtonElement).click(),
    );
    expect(close).toHaveBeenCalled();
    expect(calls).toHaveLength(1);
  });

  it('states the verdict when less than 95 % are within the tolerance', async () => {
    within = 0.824;
    render();
    await wait(200);
    expect(container.textContent).toContain(
      'Nur 82,4 % der Scanpunkte liegen in der Toleranz ±0,100 mm.',
    );
  });
});
