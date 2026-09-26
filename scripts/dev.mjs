// Development: Vite dev server for the renderer, watch builds of main and preload,
// and Electron restarted whenever main or preload change.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';

import { build, createServer } from 'vite';

import { childEnvironment, root } from './paths.mjs';

const require = createRequire(import.meta.url);
const electronBinary = require('electron');

const server = await createServer({ configFile: path.join(root, 'vite.renderer.config.ts') });
await server.listen();
const rendererUrl = `http://127.0.0.1:${server.config.server.port}`;

let electron = null;
let stopping = false;

function startElectron() {
  electron = spawn(electronBinary, ['.'], {
    cwd: root,
    stdio: 'inherit',
    env: childEnvironment({ ELECTRON_RENDERER_URL: rendererUrl }),
  });
  electron.once('exit', onElectronExit);
}

// Closing the window ends the dev session.
function onElectronExit(code) {
  if (!stopping) void stop(code ?? 0);
}

function restartElectron() {
  if (!electron) return startElectron();
  electron.off('exit', onElectronExit);
  electron.once('exit', startElectron);
  electron.kill();
}

const pending = new Set(['main', 'preload']);
for (const mode of ['main', 'preload']) {
  const watcher = await build({
    configFile: path.join(root, 'vite.main.config.ts'),
    mode,
    logLevel: 'warn',
    build: { watch: {} },
  });
  watcher.on('event', (event) => {
    if (event.code === 'ERROR') console.error(event.error);
    if (event.code !== 'END') return;
    if (pending.size) {
      pending.delete(mode);
      if (pending.size === 0) startElectron();
    } else {
      restartElectron();
    }
  });
}

async function stop(code = 0) {
  stopping = true;
  electron?.kill();
  await server.close();
  process.exit(code);
}

process.once('SIGINT', () => void stop());
process.once('SIGTERM', () => void stop());
