// Runs the project's Python with the kernel on the module path.
// Usage: node scripts/py.mjs [--cwd <dir>] <python arguments...>
import { spawnSync } from 'node:child_process';
import path from 'node:path';

import { pythonExecutable, root } from './paths.mjs';

const args = process.argv.slice(2);
let cwd = root;
if (args[0] === '--cwd') {
  cwd = path.resolve(root, args[1] ?? '.');
  args.splice(0, 2);
}

const env = { ...process.env, PYTHONPATH: path.join(root, 'kernel'), PYTHONUTF8: '1' };
delete env.PYTHONHOME;

const result = spawnSync(pythonExecutable(), args, { cwd, env, stdio: 'inherit' });
process.exit(result.status ?? 1);
