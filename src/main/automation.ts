// Local automation interface (docs/AUTOMATION.md), used by the MCP server in
// tools/mcp. It is off by default; when the user enables it in the settings, the
// main process listens on 127.0.0.1 with a random port and token and writes both
// to automation.json in the user data folder. Only processes of the same user
// can read that file, so only they can connect.
//
// Requests go the same way as the renderer's: kernel calls through the kernel
// host (the renderer receives every document change and updates the view), and
// user-interface actions (view, tools, selection) through IPC to the renderer.

import { randomBytes, timingSafeEqual } from 'node:crypto';
import { rmSync, writeFileSync } from 'node:fs';
import { type IncomingMessage, type Server, type ServerResponse, createServer } from 'node:http';

import { type BrowserWindow, ipcMain } from 'electron';

import type { AutomationAction, AutomationResponse } from '@shared/automation';
import { IPC } from '@shared/ipc';
import { decodeBuffers, encodeBuffers } from '@shared/protocol/codec';

import type { KernelHost } from './kernel/KernelHost';
import type { Logger } from './logging';

/** Face selections of a full scan (up to 2 million indices) must fit into one request. */
const MAX_BODY_BYTES = 64 * 1024 * 1024;
const UI_TIMEOUT_MS = 60_000;
/**
 * Typed arrays up to this length are returned in full (face selections, which clients
 * send back as fit input); only scene geometry is longer and comes as a summary.
 */
const INLINE_ARRAY_LENGTH = 2_000_000;

const TYPED = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  int32: Int32Array,
  float32: Float32Array,
  float64: Float64Array,
} as const;
type TypedName = keyof typeof TYPED;

export interface AutomationOptions {
  kernel: KernelHost;
  window: () => BrowserWindow | null;
  log: Logger;
  /** Where the port and token are published (automation.json in the user data folder). */
  infoPath: string;
  version: string;
}

interface RpcRequest {
  method: string;
  params?: Record<string, unknown>;
}

class RpcError extends Error {}

/** JSON values of the form {"$typed": "uint32", "values": [...]} become typed arrays. */
function toTyped(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(toTyped);
  if (typeof value !== 'object' || value === null) return value;
  const record = value as Record<string, unknown>;
  const name = record.$typed;
  if (typeof name === 'string' && name in TYPED && Array.isArray(record.values)) {
    return TYPED[name as TypedName].from(record.values as number[]);
  }
  return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, toTyped(item)]));
}

/** Typed arrays become JSON: short ones in full, long ones as length and first values. */
function fromTyped(value: unknown): unknown {
  if (ArrayBuffer.isView(value) && !(value instanceof DataView)) {
    const array = Array.from(value as unknown as ArrayLike<number>);
    if (array.length <= INLINE_ARRAY_LENGTH) return array;
    return { $typed: value.constructor.name, length: array.length, head: array.slice(0, 16) };
  }
  if (Array.isArray(value)) return value.map(fromTyped);
  if (typeof value !== 'object' || value === null) return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, fromTyped(item)]));
}

function readBody(request: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    request.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new RpcError('request too large'));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    request.on('error', reject);
  });
}

export class AutomationServer {
  private server: Server | null = null;
  private token = '';
  private nextRequestId = 1;
  private readonly waiting = new Map<number, (response: AutomationResponse) => void>();

  constructor(private readonly options: AutomationOptions) {
    ipcMain.on(IPC.automationResponse, (event, response: AutomationResponse) => {
      if (event.sender !== this.options.window()?.webContents) return;
      this.waiting.get(response.requestId)?.(response);
      this.waiting.delete(response.requestId);
    });
  }

  get running(): boolean {
    return this.server !== null;
  }

  async start(): Promise<void> {
    if (this.server) return;
    this.token = randomBytes(24).toString('hex');
    const server = createServer((request, response) => void this.serve(request, response));
    await new Promise<void>((resolve, reject) => {
      server.once('error', reject);
      server.listen(0, '127.0.0.1', () => resolve());
    });
    this.server = server;
    const address = server.address();
    const port = typeof address === 'object' && address ? address.port : 0;
    const info = { port, token: this.token, pid: process.pid, version: this.options.version };
    writeFileSync(this.options.infoPath, JSON.stringify(info, null, 2), { mode: 0o600 });
    this.options.log.info(`automation interface listening on 127.0.0.1:${port}`);
  }

  async stop(): Promise<void> {
    const server = this.server;
    this.server = null;
    rmSync(this.options.infoPath, { force: true });
    if (server) await new Promise<void>((resolve) => server.close(() => resolve()));
  }

  private authorized(request: IncomingMessage): boolean {
    const expected = Buffer.from(`Bearer ${this.token}`);
    const given = Buffer.from(request.headers.authorization ?? '');
    return given.length === expected.length && timingSafeEqual(given, expected);
  }

  private async serve(request: IncomingMessage, response: ServerResponse): Promise<void> {
    const reply = (status: number, body: unknown) => {
      response.writeHead(status, { 'content-type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    // Browsers send an Origin header; no web page may drive the application.
    if (request.headers.origin || request.method !== 'POST' || request.url !== '/rpc') {
      reply(404, { error: 'not found' });
      return;
    }
    if (!this.authorized(request)) {
      reply(401, { error: 'unauthorized' });
      return;
    }
    try {
      const { method, params = {} } = JSON.parse(await readBody(request)) as RpcRequest;
      reply(200, { ok: true, result: await this.dispatch(method, params) });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      reply(200, { ok: false, error: message });
    }
  }

  private async dispatch(method: string, params: Record<string, unknown>): Promise<unknown> {
    switch (method) {
      case 'ping':
        return { version: this.options.version, kernel: this.options.kernel.status };
      case 'kernel.call':
        return this.kernelCall(params);
      case 'ui':
        return this.ui(params.action as AutomationAction);
      case 'screenshot':
        return this.screenshot();
      default:
        throw new RpcError(`unknown method: ${method}`);
    }
  }

  private async kernelCall(params: Record<string, unknown>): Promise<unknown> {
    if (typeof params.method !== 'string') throw new RpcError('kernel.call needs a method');
    const { json, buffers } = encodeBuffers(toTyped(params.params ?? {}));
    const { response } = this.options.kernel.request({
      method: params.method,
      params: json,
      buffers: buffers.map((buffer) => new Uint8Array(buffer)),
      lane: typeof params.lane === 'string' ? params.lane : undefined,
      origin: 'main',
    });
    const raw = await response;
    if (!raw.ok) return { ok: false, error: raw.error };
    return { ok: true, result: fromTyped(decodeBuffers(raw.result, raw.buffers)) };
  }

  private ui(action: AutomationAction): Promise<unknown> {
    const window = this.options.window();
    if (!window) throw new RpcError('no application window');
    const requestId = this.nextRequestId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiting.delete(requestId);
        reject(new RpcError('the user interface did not answer'));
      }, UI_TIMEOUT_MS);
      this.waiting.set(requestId, (answer) => {
        clearTimeout(timer);
        if (answer.ok) resolve(answer.result);
        else reject(new RpcError(answer.error ?? 'failed'));
      });
      window.webContents.send(IPC.automationRequest, { requestId, action });
    });
  }

  private async screenshot(): Promise<unknown> {
    const window = this.options.window();
    if (!window) throw new RpcError('no application window');
    const image = await window.webContents.capturePage();
    return { mimeType: 'image/png', data: image.toPNG().toString('base64') };
  }
}
