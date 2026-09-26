import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** The Python interpreter of the project venv, or `M2C_PYTHON` when set. */
export function pythonExecutable() {
  if (process.env.M2C_PYTHON) return process.env.M2C_PYTHON;
  const venv = path.join(
    root,
    '.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
  );
  if (!existsSync(venv)) {
    throw new Error(
      `No Python found at ${venv}. Create the venv first (see CONTRIBUTING.md) or set M2C_PYTHON.`,
    );
  }
  return venv;
}

/** Environment for child processes: Electron must not run as plain Node. */
export function childEnvironment(extra = {}) {
  const env = { ...process.env, ...extra };
  delete env.ELECTRON_RUN_AS_NODE;
  return env;
}
