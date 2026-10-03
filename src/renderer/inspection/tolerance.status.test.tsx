// @vitest-environment happy-dom

import { act } from 'react';
import { type Root, createRoot } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { initI18n } from '../i18n';
import { setDocumentSnapshot } from '../state/documentStore';
import { TooltipProvider } from '../ui/Tooltip/Tooltip';
import { statusItem } from './tolerance.status';

const calls: { method: string; params: unknown }[] = [];

vi.mock('../kernel/kernel', () => ({
  kernel: () => ({
    call: (method: string, params: unknown) => {
      calls.push({ method, params });
      return { result: Promise.resolve({ revision: 9 }) };
    },
  }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const settings = {
  tolerance: 0.05,
  snapUnits: 'metric',
  noiseOverride: null,
  deviationMaxDistance: 2,
};

function snapshot(): DocumentSnapshot {
  return {
    revision: 8,
    cause: 'commit',
    label: 'test',
    document: { scan: { key: 'scan:a', noise: 0.036 }, settings, features: [] },
    status: { features: {}, bodies: [] },
  } as unknown as DocumentSnapshot;
}

describe('tolerance status item', () => {
  let container: HTMLDivElement;
  let root: Root;
  const Tolerance = statusItem.Component;

  beforeAll(async () => {
    await initI18n('de');
  });

  beforeEach(() => {
    calls.length = 0;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    setDocumentSnapshot(snapshot());
    act(() =>
      root.render(
        <TooltipProvider>
          <Tolerance />
        </TooltipProvider>,
      ),
    );
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    setDocumentSnapshot(null);
  });

  const byTestId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);

  it('opens the popover with noise and proposal and applies it as one settings change', async () => {
    expect(byTestId('status-tolerance')?.textContent).toBe('Toleranz ±0,050 mm');
    act(() => byTestId('status-tolerance')?.click());
    const popover = byTestId('tolerance-popover');
    expect(popover?.textContent).toContain('Scanrauschen0,036 mm');
    expect(popover?.textContent).toContain('Vorschlag aus Scanrauschen: ±0,100 mm');
    expect(popover?.textContent).toContain('unter dem 2,5-fachen Scanrauschen');

    act(() => byTestId('tolerance-use-proposal')?.click());
    const inch = [...(popover?.querySelectorAll('[role="radio"]') ?? [])].find(
      (segment) => segment.textContent === 'Zoll',
    ) as HTMLElement;
    act(() => inch.click());
    await act(async () => {
      byTestId('tolerance-apply')?.click();
      await Promise.resolve();
    });

    expect(calls).toEqual([
      {
        method: 'doc.apply',
        params: {
          baseRevision: 8,
          ops: [
            { type: 'setSettings', settings: { ...settings, tolerance: 0.1, snapUnits: 'inch' } },
          ],
          label: 'settings',
        },
      },
    ]);
    expect(byTestId('tolerance-popover')).toBeNull();
  });
});
