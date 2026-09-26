import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import type { KernelStatus } from '@shared/bridge';

import type { Logger } from '../logging';
import { KernelHost } from './KernelHost';

const FAKE_KERNEL = path.resolve(import.meta.dirname, '../../../tests/fixtures/fake-kernel.mjs');
const silent: Logger = { debug() {}, info() {}, warn() {}, error() {} };

let host: KernelHost | null = null;

function startHost(env: NodeJS.ProcessEnv = {}, cancelGraceMs = 300): KernelHost {
  host = new KernelHost({
    locate: () => ({ command: process.execPath, args: [FAKE_KERNEL], env: { ...process.env, ...env } }),
    log: silent,
    cancelGraceMs,
    readyTimeoutMs: 10_000,
  });
  return host;
}

afterEach(async () => {
  await host?.stop();
  host = null;
});

describe('KernelHost', () => {
  it('reports ready after the kernel starts', async () => {
    const kernel = startHost();
    await kernel.start();
    expect(kernel.status.state).toBe('ready');
  });

  it('routes responses and binary buffers to their requests', async () => {
    const kernel = startHost();
    await kernel.start();
    const data = new Float32Array([1.5, 2.5, 3.5]);
    const first = kernel.request({ method: 'echo', params: { value: 1 }, buffers: [data], origin: 'renderer' });
    const second = kernel.request({ method: 'echo', params: { value: 2 }, lane: 'echo:tool', origin: 'main' });

    const [a, b] = await Promise.all([first.response, second.response]);
    expect(a.ok && a.result).toEqual({ params: { value: 1 }, origin: 'renderer', lane: null });
    expect(a.ok && Array.from(new Float32Array(a.buffers[0]!))).toEqual([1.5, 2.5, 3.5]);
    expect(b.ok && b.result).toEqual({ params: { value: 2 }, origin: 'main', lane: 'echo:tool' });
  });

  it('passes progress events to the request that caused them', async () => {
    const kernel = startHost();
    await kernel.start();
    const fractions: (number | null)[] = [];
    const { response } = kernel.request({ method: 'progress', params: { steps: 4 }, origin: 'renderer' }, (fraction) =>
      fractions.push(fraction),
    );
    await response;
    expect(fractions).toEqual([0.25, 0.5, 0.75, 1]);
  });

  it('resolves a cancelled request at once, even while the kernel is blocked', async () => {
    const kernel = startHost();
    await kernel.start();
    const { id, response } = kernel.request({ method: 'hang', params: { ms: 1000 }, origin: 'renderer' });
    const start = Date.now();
    kernel.cancel(id);
    const result = await response;
    expect(result).toMatchObject({ ok: false, error: { code: 'kernel.cancelled' } });
    expect(Date.now() - start).toBeLessThan(100);
  });

  it('reports an unresponsive kernel when a cancelled request keeps running, and recovers', async () => {
    const kernel = startHost({}, 200);
    await kernel.start();
    const states: KernelStatus['state'][] = [];
    kernel.onStatus((status) => states.push(status.state));
    const { id } = kernel.request({ method: 'hang', params: { ms: 600 }, origin: 'renderer' });
    kernel.cancel(id);
    await new Promise((resolve) => setTimeout(resolve, 900));
    expect(states).toEqual(['unresponsive', 'ready']);
  });

  it('fails open requests and reports the exit when the kernel crashes', async () => {
    const kernel = startHost();
    await kernel.start();
    const pending = kernel.request({ method: 'sleep', params: { ms: 5000 }, origin: 'renderer' });
    kernel.request({ method: 'crash', params: {}, origin: 'renderer' });
    expect(await pending.response).toMatchObject({ ok: false, error: { code: 'kernel.stopped' } });
    expect(kernel.status).toMatchObject({ state: 'stopped', exitCode: 3 });
    const late = kernel.request({ method: 'echo', params: {}, origin: 'renderer' });
    expect(await late.response).toMatchObject({ ok: false, error: { code: 'kernel.stopped' } });
  });

  it('restarts after a crash', async () => {
    const kernel = startHost();
    await kernel.start();
    await kernel.request({ method: 'crash', params: {}, origin: 'renderer' }).response;
    await kernel.restart();
    const { response } = kernel.request({ method: 'echo', params: { again: true }, origin: 'renderer' });
    expect(await response).toMatchObject({ ok: true });
  });

  it('refuses a kernel with a different protocol version', async () => {
    const kernel = startHost({ FAKE_KERNEL_PROTOCOL: '99' });
    await expect(kernel.start()).rejects.toThrow('protocol');
    expect(kernel.status).toMatchObject({ state: 'stopped', error: { code: 'kernel.protocolMismatch' } });
  });
});
