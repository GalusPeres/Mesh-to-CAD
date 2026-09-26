// Fails when the application and the kernel versions differ; they are always released together.
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { root } from './paths.mjs';

const app = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8')).version;
const init = readFileSync(path.join(root, 'kernel', 'm2c_kernel', '__init__.py'), 'utf8');
const kernel = /__version__\s*=\s*"([^"]+)"/.exec(init)?.[1];

if (app !== kernel) {
  console.error(`Version mismatch: package.json ${app}, kernel ${kernel ?? 'not found'}.`);
  process.exit(1);
}
console.log(`Versions match: ${app}`);
