// Starts the built application (after `npm run build`) without the dev server.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';

import { childEnvironment, root } from './paths.mjs';

const require = createRequire(import.meta.url);
const child = spawn(require('electron'), ['.'], {
  cwd: root,
  stdio: 'inherit',
  env: childEnvironment(),
});
child.on('exit', (code) => process.exit(code ?? 0));
