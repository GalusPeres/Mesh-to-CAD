import { describe, expect, it, vi } from 'vitest';

import type { KernelEvent, KernelRequest, M2CBridge, RawResponse } from '@shared/bridge';

import { KernelClient } from './KernelClient';
import { KernelFailure, isSilentFailure } from './KernelFailure';

function fakeBridge(respond: (request: KernelRequest) => RawResponse) {
  let emit: (event: KernelEvent) => void = () => undefined;
  const request = vi.fn((sent: KernelRequest) => Promise.resolve(respond(sent)));
  const bridge: M2CBridge['kernel'] = {
    request,
    cancel: vi.fn(),
    restart: vi.fn(),
    status: vi.fn(),
    onEvent: (listener) => {
      emit = listener;
      return () => undefined;
    },
    onStatus: () => () => undefined,
  };
  return { bridge, request, emit: (event: KernelEvent) => emit(event) };
}

describe('KernelClient', () => {
  it('sends typed arrays as buffers and decodes buffers in results', async () => {
    const { bridge, request } = fakeBridge((sent) => ({
      ok: true,
      result: { echoed: sent.params, values: { $buf: 0, dtype: 'float32', shape: [2] } },
      buffers: [new Float32Array([1, 2]).buffer],
    }));
    const client = new KernelClient(bridge);
    const job = client.call('scene.fetch', { keys: ['a'] }, { lane: 'scene.fetch:test' });
    const result = (await job.result) as unknown as { echoed: unknown; values: Float32Array };

    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({ method: 'scene.fetch', lane: 'scene.fetch:test', buffers: [] }),
    );
    expect(result.echoed).toEqual({ keys: ['a'] });
    expect(Array.from(result.values)).toEqual([1, 2]);
  });

  it('rejects with a KernelFailure carrying the code and parameters', async () => {
    const { bridge } = fakeBridge(() => ({
      ok: false,
      error: { code: 'mesh.empty', params: { fileName: 'a.stl' } },
    }));
    const failure = await new KernelClient(bridge).call('doc.get', {}).result.catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(KernelFailure);
    expect(failure).toMatchObject({ code: 'mesh.empty', params: { fileName: 'a.stl' } });
    expect(isSilentFailure(failure)).toBe(false);
  });

  it('reports progress to the job and to the observer', async () => {
    let finish: (response: RawResponse) => void = () => undefined;
    const { bridge, emit } = fakeBridge(() => ({ ok: true, result: {}, buffers: [] }));
    bridge.request = () => new Promise((resolve) => (finish = resolve));
    const observer = { started: vi.fn(), progress: vi.fn(), finished: vi.fn() };
    const job = new KernelClient(bridge, observer).call('doc.get', {});
    const seen: (number | null)[] = [];
    job.onProgress((fraction) => seen.push(fraction));

    emit({ type: 'progress', clientId: job.clientId, fraction: 0.5, stage: 'kernel.working' });
    finish({ ok: true, result: {}, buffers: [] });
    await job.result;

    expect(seen).toEqual([0.5]);
    expect(observer.started).toHaveBeenCalledWith(expect.objectContaining({ method: 'doc.get' }));
    expect(observer.finished).toHaveBeenCalledWith(job.clientId);
  });

  it('treats cancelled and superseded requests as silent', () => {
    expect(isSilentFailure(new KernelFailure({ code: 'kernel.superseded', params: {} }))).toBe(true);
    expect(isSilentFailure(new Error('x'))).toBe(false);
  });
});
