// Builds the renderer, the main process and the preload script into dist/.
import path from 'node:path';

import { build } from 'vite';

import { root } from './paths.mjs';

const renderer = path.join(root, 'vite.renderer.config.ts');
const electron = path.join(root, 'vite.main.config.ts');

await build({ configFile: renderer, logLevel: 'warn' });
await build({ configFile: electron, mode: 'main', logLevel: 'warn' });
await build({ configFile: electron, mode: 'preload', logLevel: 'warn' });
console.log('Built renderer, main and preload into dist/.');
