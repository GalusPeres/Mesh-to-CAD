// Smoke test of a frozen kernel: start it the way the application does, then check
// the handshake, `system.info` (including the Open CASCADE version), that native
// writes to stdout cannot corrupt the protocol stream, and a clean shutdown.
//
//   node scripts/kernel-smoke.mjs [path\to\m2c-kernel.exe]
//
// Without an argument it uses M2C_KERNEL_EXE or release/kernel/m2c-kernel.exe.

import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { childEnvironment, root } from './paths.mjs';

const MAGIC = Buffer.from('M2CF', 'ascii');
const PREFIX_BYTES = 12;
const padding = (length) => (8 - (length % 8)) % 8;

function encodeFrame(header) {
  const json = Buffer.from(JSON.stringify({ ...header, buffers: [] }), 'utf8');
  const prefix = Buffer.alloc(PREFIX_BYTES);
  MAGIC.copy(prefix, 0);
  prefix.writeUInt32LE(json.length, 4);
  prefix.writeUInt32LE(0, 8);
  return Buffer.concat([prefix, json, Buffer.alloc(padding(PREFIX_BYTES + json.length))]);
}

/** Splits the kernel's stdout into frame headers; anything else is protocol corruption. */
class FrameReader {
  #pending = Buffer.alloc(0);

  push(chunk) {
    this.#pending = Buffer.concat([this.#pending, chunk]);
    const headers = [];
    while (this.#pending.length >= PREFIX_BYTES) {
      if (!this.#pending.subarray(0, 4).equals(MAGIC)) {
        const preview = this.#pending.subarray(0, 40).toString('latin1');
        throw new Error(`stdout carries bytes outside a frame: ${JSON.stringify(preview)}`);
      }
      const headerLength = this.#pending.readUInt32LE(4);
      const bodyLength = this.#pending.readUInt32LE(8);
      const headerEnd = PREFIX_BYTES + headerLength;
      const total = headerEnd + padding(headerEnd) + bodyLength;
      if (this.#pending.length < total) break;
      headers.push(JSON.parse(this.#pending.subarray(PREFIX_BYTES, headerEnd).toString('utf8')));
      this.#pending = this.#pending.subarray(total);
    }
    return headers;
  }
}

class KernelSession {
  #nextId = 1;
  #waiting = new Map();
  #events = [];
  #eventWaiters = [];
  #reader = new FrameReader();
  failure = null;
  stderr = '';

  constructor(executable, sessionDirectory) {
    this.process = spawn(executable, ['--session-dir', sessionDirectory], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
      env: childEnvironment({
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
        M2C_LOG_LEVEL: 'WARNING',
        M2C_DEBUG_COMMANDS: '1',
      }),
    });
    this.exited = new Promise((resolve) => this.process.on('exit', (code) => resolve(code)));
    this.process.stderr.on('data', (chunk) => (this.stderr += chunk.toString('utf8')));
    this.process.stdout.on('data', (chunk) => {
      try {
        for (const header of this.#reader.push(chunk)) this.#dispatch(header);
      } catch (error) {
        this.failure = error;
        for (const { reject } of this.#waiting.values()) reject(error);
      }
    });
  }

  #dispatch(header) {
    if (header.type === 'response') {
      this.#waiting.get(header.id)?.resolve(header);
      this.#waiting.delete(header.id);
      return;
    }
    this.#events.push(header);
    for (const waiter of this.#eventWaiters.splice(0)) waiter();
  }

  async event(name, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const found = this.#events.find((event) => event.event === name);
      if (found) return found;
      if (this.failure) throw this.failure;
      const left = deadline - Date.now();
      if (left <= 0) throw new Error(`no "${name}" event within ${timeoutMs} ms`);
      let timer;
      await Promise.race([
        new Promise((resolve) => this.#eventWaiters.push(resolve)),
        new Promise((resolve) => (timer = setTimeout(resolve, left))),
      ]);
      clearTimeout(timer);
    }
  }

  call(method, params = {}, { origin = 'renderer', timeoutMs = 60_000 } = {}) {
    const id = this.#nextId++;
    let timer;
    const response = new Promise((resolve, reject) => {
      this.#waiting.set(id, { resolve, reject });
      timer = setTimeout(
        () => reject(new Error(`${method} did not answer within ${timeoutMs} ms`)),
        timeoutMs,
      );
    });
    this.process.stdin.write(encodeFrame({ type: 'request', id, method, params, origin }));
    return response
      .then((header) => {
        if (!header.ok) throw new Error(`${method} failed: ${JSON.stringify(header.error)}`);
        return header.result;
      })
      .finally(() => clearTimeout(timer));
  }
}

function defaultExecutable() {
  return (
    process.argv[2] ??
    process.env.M2C_KERNEL_EXE ??
    path.join(root, 'release', 'kernel', 'm2c-kernel.exe')
  );
}

export async function runKernelSmoke(executable = defaultExecutable()) {
  if (!existsSync(executable)) throw new Error(`kernel executable not found: ${executable}`);
  const expectedVersion = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8')).version;
  const sessionDirectory = mkdtempSync(path.join(tmpdir(), 'm2c-kernel-smoke-'));
  const started = Date.now();
  const kernel = new KernelSession(executable, sessionDirectory);
  try {
    const ready = await kernel.event('ready', 60_000);
    const readyMs = Date.now() - started;
    const info = await kernel.call('system.info');
    const infoMs = Date.now() - started;
    if (!/^\d+\.\d+/.test(info.occtVersion ?? '')) {
      throw new Error(`system.info reports no OCCT version: ${JSON.stringify(info)}`);
    }
    if (info.kernelVersion !== expectedVersion) {
      throw new Error(`kernel ${info.kernelVersion} does not match the app ${expectedVersion}`);
    }
    await kernel.call('debug.stdoutNoise');
    await kernel.call('system.ping');
    await kernel.call('system.shutdown', {}, { origin: 'main' });
    let timer;
    const exitCode = await Promise.race([
      kernel.exited,
      new Promise((resolve) => (timer = setTimeout(() => resolve('timeout'), 10_000))),
    ]);
    clearTimeout(timer);
    if (exitCode !== 0) throw new Error(`kernel exited with ${exitCode} after shutdown`);
    return {
      executable,
      protocolVersion: ready.data?.protocolVersion,
      kernelVersion: info.kernelVersion,
      occtVersion: info.occtVersion,
      pythonVersion: info.pythonVersion,
      readyMs,
      infoMs,
    };
  } catch (error) {
    kernel.process.kill();
    const log = kernel.stderr.trim().split(/\r?\n/).slice(-20).join('\n');
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`${message}\n${log}`, { cause: error });
  } finally {
    await kernel.exited;
    rmSync(sessionDirectory, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runKernelSmoke()
    .then((summary) => {
      console.log('Kernel smoke test passed:');
      console.log(JSON.stringify(summary, null, 2));
    })
    .catch((error) => {
      console.error(`Kernel smoke test failed: ${error.message}`);
      process.exit(1);
    });
}
