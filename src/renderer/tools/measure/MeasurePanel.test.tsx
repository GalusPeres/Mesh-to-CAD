// @vitest-environment happy-dom

import { act } from 'react';
import { type Root, createRoot } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { MeasureResult } from '@shared/protocol/generated/inspection';

import { initI18n } from '../../i18n';
import { setDocumentSnapshot } from '../../state/documentStore';
import { selectObjects } from '../../state/objectSelectionStore';
import { TooltipProvider } from '../../ui/Tooltip/Tooltip';
import { MeasurePanel } from './MeasurePanel';

const calls: { method: string; params: unknown }[] = [];
const planes: MeasureResult = {
  kindA: 'plane',
  kindB: 'plane',
  distance: { value: 20.0012, uncertainty: 0.0003 },
  distanceKind: 'parallel',
  angleDeg: { value: 0.004, uncertainty: 0.002 },
  parallel: true,
  diameterA: null,
  diameterB: null,
};

vi.mock('../../kernel/kernel', () => ({
  kernel: () => ({
    call: (method: string, params: unknown) => {
      calls.push({ method, params });
      return { result: Promise.resolve(planes) };
    },
  }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function snapshot(): DocumentSnapshot {
  const fit = (id: string) => ({
    id,
    type: 'fit',
    name: null,
    suppressed: false,
    params: { kind: 'plane' },
  });
  return {
    revision: 4,
    cause: 'commit',
    label: 'test',
    document: { scan: { key: 'scan:a' }, features: [fit('f2'), fit('f3')] },
    status: {
      features: {
        f2: { state: 'ok', issues: [], error: null, stats: {} },
        f3: { state: 'ok', issues: [], error: null, stats: {} },
      },
      bodies: [],
    },
  } as unknown as DocumentSnapshot;
}

describe('measure panel', () => {
  let container: HTMLDivElement;
  let root: Root;

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
    setDocumentSnapshot(null);
    selectObjects([]);
  });

  const wait = (ms: number) => act(async () => new Promise((resolve) => setTimeout(resolve, ms)));

  it('measures between two fits picked in the tree and shows the uncertainty', async () => {
    act(() =>
      root.render(
        <TooltipProvider>
          <MeasurePanel activation={null} editTarget={null} close={() => undefined} />
        </TooltipProvider>,
      ),
    );
    act(() => selectObjects([{ kind: 'feature', id: 'f2' }]));
    act(() => selectObjects([{ kind: 'feature', id: 'f3' }]));
    await wait(200);

    expect(calls.at(-1)).toEqual({
      method: 'inspection.measure',
      params: { a: { type: 'feature', feature: 'f2' }, b: { type: 'feature', feature: 'f3' } },
    });
    const result = container.querySelector('[data-testid="measure-result"]')?.textContent ?? '';
    expect(result).toContain('Abstand20,001 mm ± 0,0003');
    expect(result).toContain('Winkel0,00° ± 0,002');
    const first = container.querySelector('[data-testid="measure-item-0"]') as HTMLSelectElement;
    expect(first.value).toBe('feature:f2');
  });
});
