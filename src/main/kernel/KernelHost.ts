import { type ChildProcessWithoutNullStreams, spawn } from 'node:child_process';

import type { KernelErrorPayload, KernelStatus, RawResponse } from '@shared/bridge';
import { FrameError, FrameReader, encodeFrame } from '@shared/protocol/frame';
import { CANCEL_GRACE_MS } from '@shared/protocol/generated/limits';
import { PROTOCOL_VERSION } from '@shared/protocol/generated/protocol';

import type { Logger } from '../logging';

export interface KernelCommand {
  command: string;
  args: string[];
  cwd?: string;
  env: NodeJS.ProcessEnv;
}

export interface HostRequest {
  method: string;
  params: unknown;
  buffers?: readonly ArrayBufferView[];
  lane?: string;
  origin: 'renderer' | 'main';
}

export type ProgressListener = (fraction: number | null, stage: string) => void;

export interface KernelHostOptions {
  /** Resolves the command on every start, so a restart picks up a new session directory. */
  locate: () => KernelCommand;
  log: Logger;
  /** Receives each line the kernel writes to stderr (its log). */
  onKernelLog?: (line: string) => void;
  readyTimeoutMs?: number;
  cancelGraceMs?: number;
  shutdownTimeoutMs?: number;
}

interface Pending {
  method: string;
  resolve: (response: RawResponse) => void;
  onProgress?: ProgressListener;
}

type DocumentListener = (data: unknown) => void;
type StatusListener = (status: KernelStatus) => void;

function failure(code: string, params: Record<string, unknown> = {}, details?: string): RawResponse {
  const error: KernelErrorPayload = details ? { code, params, details } : { code, params };
  return { ok: false, error };
}

/**
 * Owns the kernel process: spawns it, frames requests, routes responses and
 * events, and restarts it on request.
 *
 * Cancellation never waits for the kernel. Native calls in the kernel (Open
 * CASCADE, mesh decimation) hold the Python GIL, and while they run the kernel
 * cannot even read the cancel message. `cancel` therefore resolves the request
 * at once with `kernel.cancelled`; if the kernel has not finished the abandoned
 * request after `cancelGraceMs`, the status becomes `unresponsive` and the
 * application offers a restart.
 */
export class KernelHost {
  private process: ChildProcessWithoutNullStreams | null = null;
  private reader = new FrameReader();
  private pending = new Map<number, Pending>();
  private abandoned = new Map<number, ReturnType<typeof setTimeout>>();
  private nextId = 1;
  private currentStatus: KernelStatus = { state: 'stopped' };
  private stopping = false;
  private readyWaiter: { resolve: () => void; reject: (error: Error) => void } | null = null;
  private readonly documentListeners = new Set<DocumentListener>();
  private readonly statusListeners = new Set<StatusListener>();

  constructor(private readonly options: KernelHostOptions) {}

  get status(): KernelStatus {
    return this.currentStatus;
  }

  onDocumentChanged(listener: DocumentListener): () => void {
    this.documentListeners.add(listener);
    return () => this.documentListeners.delete(listener);
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  /** Start the kernel and wait for its `ready` event. */
  async start(): Promise<void> {
    if (this.process) return;
    const { command, args, cwd, env } = this.options.locate();
    this.stopping = false;
    this.reader = new FrameReader();
    this.setStatus({ state: 'starting' });
    this.options.log.info(`starting kernel: ${command} ${args.join(' ')}`);

    const child = spawn(command, args, { cwd, env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    this.process = child;
    child.stdout.on('data', (chunk: Buffer) => this.receive(chunk));
    child.stderr.setEncoding('utf8');
    let partial = '';
    child.stderr.on('data', (text: string) => {
      const lines = (partial + text).split(/\r?\n/);
      partial = lines.pop() ?? '';
      for (const line of lines) if (line) this.options.onKernelLog?.(line);
    });
    child.on('error', (error) => this.handleExit(null, error));
    child.on('exit', (code) => this.handleExit(code));

    const ready = new Promise<void>((resolve, reject) => {
      this.readyWaiter = { resolve, reject };
    });
    const timeout = setTimeout(() => {
      this.readyWaiter?.reject(new Error('kernel did not report ready in time'));
      this.readyWaiter = null;
      child.kill();
    }, this.options.readyTimeoutMs ?? 30_000);
    try {
      await ready;
    } finally {
      clearTimeout(timeout);
    }
  }

  /** Send a request; the promise always resolves (failures are error responses). */
  request(request: HostRequest, onProgress?: ProgressListener): { id: number; response: Promise<RawResponse> } {
    const id = this.nextId++;
    const child = this.process;
    if (!child || this.currentStatus.state === 'stopped' || this.currentStatus.state === 'starting') {
      return { id, response: Promise.resolve(failure('kernel.stopped')) };
    }
    const response = new Promise<RawResponse>((resolve) => {
      this.pending.set(id, { method: request.method, resolve, onProgress });
    });
    const header: Record<string, unknown> = {
      type: 'request',
      id,
      method: request.method,
      params: request.params ?? {},
      origin: request.origin,
    };
    if (request.lane) header.lane = request.lane;
    try {
      for (const chunk of encodeFrame(header, request.buffers ?? [])) child.stdin.write(chunk);
    } catch (error) {
      this.pending.delete(id);
      const details = error instanceof Error ? error.message : String(error);
      return { id, response: Promise.resolve(failure('kernel.invalidParams', {}, details)) };
    }
    return { id, response };
  }

  /** Cancel a request. It resolves immediately; the kernel stops it when it can. */
  cancel(id: number): void {
    const pending = this.pending.get(id);
    if (!pending) return;
    this.pending.delete(id);
    pending.resolve(failure('kernel.cancelled'));
    this.write({ type: 'cancel', id });
    const timer = setTimeout(() => {
      if (this.abandoned.has(id) && this.currentStatus.state === 'ready') {
        this.options.log.warn(`request ${id} (${pending.method}) still running after cancel`);
        this.setStatus({ state: 'unresponsive' });
      }
    }, this.options.cancelGraceMs ?? CANCEL_GRACE_MS);
    this.abandoned.set(id, timer);
  }

  /** Stop the kernel (if running) and start it again on the same session. */
  async restart(): Promise<void> {
    await this.stop({ graceful: false });
    await this.start();
  }

  /** Ask the kernel to shut down; kill it if it does not exit in time. */
  async stop({ graceful = true } = {}): Promise<void> {
    const child = this.process;
    if (!child) return;
    this.stopping = true;
    const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()));
    if (graceful && this.currentStatus.state !== 'stopped') {
      this.request({ method: 'system.shutdown', params: {}, origin: 'main' });
      child.stdin.end();
    } else {
      child.kill();
    }
    const timeout = setTimeout(() => child.kill(), this.options.shutdownTimeoutMs ?? 5_000);
    await exited;
    clearTimeout(timeout);
  }

  private write(header: Record<string, unknown>): void {
    const child = this.process;
    if (!child) return;
    for (const chunk of encodeFrame(header)) child.stdin.write(chunk);
  }

  private receive(chunk: Buffer): void {
    let frames;
    try {
      frames = this.reader.push(chunk);
    } catch (error) {
      const message = error instanceof FrameError ? error.message : String(error);
      this.options.log.error(`protocol error from kernel: ${message}`);
      this.process?.kill();
      return;
    }
    for (const frame of frames) this.dispatch(frame.header, frame.buffers);
  }

  private dispatch(header: Record<string, unknown>, buffers: Uint8Array[]): void {
    if (header.type === 'response') {
      this.resolveResponse(header, buffers);
    } else if (header.type === 'event') {
      this.handleEvent(header);
    }
  }

  private resolveResponse(header: Record<string, unknown>, buffers: Uint8Array[]): void {
    const id = Number(header.id);
    const timer = this.abandoned.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      this.abandoned.delete(id);
      if (this.abandoned.size === 0 && this.currentStatus.state === 'unresponsive') {
        this.setStatus({ state: 'ready' });
      }
      return;
    }
    const pending = this.pending.get(id);
    if (!pending) return;
    this.pending.delete(id);
    if (header.ok === true) {
      // Copy each buffer into its own ArrayBuffer: the frame bytes are reused, and
      // the renderer receives standalone buffers it can transfer to workers.
      const copies = buffers.map((buffer) => new Uint8Array(buffer).buffer);
      pending.resolve({ ok: true, result: header.result, buffers: copies });
    } else {
      pending.resolve({ ok: false, error: header.error as KernelErrorPayload });
    }
  }

  private handleEvent(header: Record<string, unknown>): void {
    const data = header.data as Record<string, unknown> | undefined;
    switch (header.event) {
      case 'ready':
        this.handleReady(data ?? {});
        break;
      case 'progress': {
        const pending = this.pending.get(Number(header.requestId));
        const fraction = data?.fraction;
        const stage = typeof data?.stage === 'string' ? data.stage : '';
        pending?.onProgress?.(typeof fraction === 'number' ? fraction : null, stage);
        break;
      }
      case 'documentChanged':
        for (const listener of this.documentListeners) listener(data);
        break;
      default:
        this.options.log.warn(`unknown kernel event ${String(header.event)}`);
    }
  }

  private handleReady(data: Record<string, unknown>): void {
    const waiter = this.readyWaiter;
    this.readyWaiter = null;
    if (data.protocolVersion !== PROTOCOL_VERSION) {
      const error = { code: 'kernel.protocolMismatch', params: { expected: PROTOCOL_VERSION, actual: String(data.protocolVersion) } };
      this.setStatus({ state: 'stopped', error });
      waiter?.reject(new Error('kernel protocol version mismatch'));
      this.process?.kill();
      return;
    }
    this.options.log.info(`kernel ready (kernel ${String(data.kernelVersion)}, Python ${String(data.pythonVersion)})`);
    this.setStatus({ state: 'ready' });
    waiter?.resolve();
  }

  private handleExit(code: number | null, error?: Error): void {
    if (!this.process) return;
    this.process = null;
    if (error) this.options.log.error('kernel process error', error);
    this.options.log.info(`kernel exited with code ${String(code)}`);
    for (const pending of this.pending.values()) pending.resolve(failure('kernel.stopped'));
    this.pending.clear();
    for (const timer of this.abandoned.values()) clearTimeout(timer);
    this.abandoned.clear();
    this.readyWaiter?.reject(new Error(`kernel exited during start (code ${String(code)})`));
    this.readyWaiter = null;
    if (this.currentStatus.state === 'stopped' && this.currentStatus.error) return;
    this.setStatus(this.stopping ? { state: 'stopped' } : { state: 'stopped', exitCode: code });
  }

  private setStatus(status: KernelStatus): void {
    this.currentStatus = status;
    for (const listener of this.statusListeners) listener(status);
  }
}
