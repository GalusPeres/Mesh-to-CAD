import type { KernelEvent, M2CBridge, Unsubscribe } from '@shared/bridge';
import { decodeBuffers, encodeBuffers } from '@shared/protocol/codec';
import { type KernelMethods, METHOD_TABLE, type MethodName } from '@shared/protocol/generated/index';

import { KernelFailure } from './KernelFailure';

export type ParamsOf<M extends MethodName> = KernelMethods[M]['params'];
export type ResultOf<M extends MethodName> = KernelMethods[M]['result'];
export type ProgressListener = (fraction: number | null, stage: string) => void;

export interface KernelJob<T> {
  readonly clientId: number;
  readonly result: Promise<T>;
  onProgress(listener: ProgressListener): Unsubscribe;
  cancel(): void;
}

/** Notified about every job, e.g. to show progress in the status bar. */
export interface JobObserver {
  started(job: { clientId: number; method: string; lane: string | null; exclusive: boolean }): void;
  progress(clientId: number, fraction: number | null, stage: string): void;
  finished(clientId: number): void;
}

type KernelBridge = M2CBridge['kernel'];

/**
 * Typed access to the kernel. Typed arrays in parameters travel as binary
 * buffers; typed arrays in results are views on the received buffers.
 *
 *     const job = kernel.call('doc.preview', { baseRevision, ops }, { lane: 'doc.preview:fit' });
 *     const result = await job.result;
 */
export class KernelClient {
  private nextClientId = 1;
  private readonly progressListeners = new Map<number, Set<ProgressListener>>();

  constructor(
    private readonly bridge: KernelBridge,
    private readonly observer: JobObserver | null = null,
  ) {
    bridge.onEvent((event: KernelEvent) => {
      if (event.type !== 'progress') return;
      this.observer?.progress(event.clientId, event.fraction, event.stage);
      for (const listener of this.progressListeners.get(event.clientId) ?? []) {
        listener(event.fraction, event.stage);
      }
    });
  }

  call<M extends MethodName>(
    method: M,
    params: ParamsOf<M>,
    options: { lane?: string } = {},
  ): KernelJob<ResultOf<M>> {
    const clientId = this.nextClientId++;
    const info = (METHOD_TABLE as Record<string, { exclusive: boolean } | undefined>)[method];
    const { json, buffers } = encodeBuffers(params);
    this.progressListeners.set(clientId, new Set());
    this.observer?.started({ clientId, method, lane: options.lane ?? null, exclusive: info?.exclusive ?? false });

    const result = this.bridge
      .request({ clientId, method, params: json, buffers, lane: options.lane })
      .then((response) => {
        if (!response.ok) throw new KernelFailure(response.error);
        return decodeBuffers(response.result, response.buffers) as ResultOf<M>;
      })
      .finally(() => {
        this.progressListeners.delete(clientId);
        this.observer?.finished(clientId);
      });

    return {
      clientId,
      result,
      onProgress: (listener) => {
        this.progressListeners.get(clientId)?.add(listener);
        return () => this.progressListeners.get(clientId)?.delete(listener);
      },
      cancel: () => this.bridge.cancel(clientId),
    };
  }
}
