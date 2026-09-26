// @vitest-environment happy-dom

import { act } from 'react';
import { type Root, createRoot } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { M2CBridge } from '@shared/bridge';
import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { PreflightResult } from '@shared/protocol/generated/export';

import { initI18n } from '../../i18n';
import { setDocumentSnapshot } from '../../state/documentStore';
import { TooltipProvider } from '../../ui/Tooltip/Tooltip';
import { ExportStepPanel } from './ExportStepPanel';

const preflight: PreflightResult = {
  exportable: false,
  bodies: [
    {
      body: 'f5',
      owner: 'f5',
      valid: true,
      closed: true,
      solids: 1,
      volume: 1234.5,
      maxTolerance: 1e-7,
      problems: [],
      blocking: false,
    },
    {
      body: 'f9',
      owner: 'f7',
      valid: true,
      closed: false,
      solids: 1,
      volume: 10,
      maxTolerance: 1e-7,
      problems: ['export.notClosed'],
      blocking: true,
    },
  ],
};

vi.mock('../../kernel/kernel', () => ({
  kernel: () => ({
    call: (method: string) => ({
      result:
        method === 'export.preflight'
          ? Promise.resolve(preflight)
          : Promise.reject(new Error(`unexpected ${method}`)),
    }),
  }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function snapshot(): DocumentSnapshot {
  const feature = (id: string) => ({
    id,
    type: 'extrude',
    name: null,
    suppressed: false,
    params: {},
  });
  return {
    revision: 7,
    cause: 'commit',
    label: 'test',
    document: {
      scan: { key: 'scan:a', source: { fileName: 'halterung.stl' } },
      settings: { tolerance: 0.1 },
      features: [feature('f5'), feature('f7'), feature('f9')],
    },
    status: {
      features: {},
      bodies: [
        { id: 'f5', owner: 'f5' },
        { id: 'f9', owner: 'f7' },
      ],
    },
  } as unknown as DocumentSnapshot;
}

describe('STEP export panel', () => {
  let container: HTMLDivElement;
  let root: Root;
  const run = vi.fn<M2CBridge['files']['run']>();
  const reveal = vi.fn<M2CBridge['files']['reveal']>();

  beforeAll(async () => {
    await initI18n('de');
  });

  beforeEach(() => {
    run.mockResolvedValue({
      ok: true,
      result: { fileName: 'halterung.step', bytes: 188_416, bodies: 1, triangles: null },
      buffers: [],
      revealToken: 'token-1',
    });
    (window as unknown as { m2c: unknown }).m2c = { files: { run, reveal } };
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    setDocumentSnapshot(snapshot());
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    setDocumentSnapshot(null);
    vi.clearAllMocks();
  });

  const settle = () => act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
  const byTestId = (id: string) => container.querySelector(`[data-testid="${id}"]`);

  it('blocks the open body, exports the valid one and offers to open the folder', async () => {
    act(() =>
      root.render(
        <TooltipProvider>
          <ExportStepPanel activation={null} editTarget={null} close={() => undefined} />
        </TooltipProvider>,
      ),
    );
    await settle();

    const text = container.textContent ?? '';
    expect(text).toContain(
      'Export gesperrt: Körper 2 ist nicht geschlossen (Ursache: Extrusion 2).',
    );
    expect((byTestId('export-body-f5') as HTMLInputElement).checked).toBe(true);
    expect((byTestId('export-body-f9') as HTMLInputElement).disabled).toBe(true);
    expect(text).toContain('halterung');

    await act(async () => {
      (byTestId('panel-ok') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    await settle();

    expect(run).toHaveBeenCalledWith(
      'exportStep',
      { bodies: ['f5'], names: ['halterung'], schema: 'AP214' },
      { title: 'STEP exportieren', filterName: 'STEP-Dateien', defaultName: 'halterung.step' },
    );
    expect(byTestId('export-done')?.textContent).toContain(
      'STEP gespeichert: halterung.step (1 Körper, 184 KB)',
    );
    const open = [...container.querySelectorAll('button')].find(
      (button) => button.textContent === 'Ordner öffnen',
    );
    act(() => open?.click());
    expect(reveal).toHaveBeenCalledWith('token-1');
  });
});
