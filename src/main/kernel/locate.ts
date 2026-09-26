import { existsSync } from 'node:fs';
import path from 'node:path';

import type { KernelCommand } from './KernelHost';

/** Environment for the kernel: no inherited Python paths, UTF-8 everywhere. */
export function kernelEnvironment(extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env, ...extra };
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
  delete env.ELECTRON_RUN_AS_NODE;
  env.PYTHONUTF8 = '1';
  env.PYTHONIOENCODING = 'utf-8';
  env.M2C_LOG_LEVEL ??= 'INFO';
  return env;
}

/**
 * The kernel command: the PyInstaller build in a packaged app, otherwise the
 * project venv (`M2C_PYTHON` overrides the interpreter).
 */
export function locateKernel(options: {
  packaged: boolean;
  resourcesPath: string;
  repositoryRoot: string;
  sessionDirectory: string;
}): KernelCommand {
  const sessionArgs = ['--session-dir', options.sessionDirectory];
  if (options.packaged) {
    const executable = path.join(options.resourcesPath, 'kernel', 'm2c-kernel.exe');
    if (!existsSync(executable)) {
      throw new Error(`The geometry kernel is missing (${executable}). Reinstall Mesh-to-CAD.`);
    }
    return { command: executable, args: sessionArgs, env: kernelEnvironment() };
  }
  const python =
    process.env.M2C_PYTHON ?? path.join(options.repositoryRoot, '.venv', 'Scripts', 'python.exe');
  return {
    command: python,
    args: ['-X', 'utf8', '-u', '-m', 'm2c_kernel', ...sessionArgs],
    cwd: path.join(options.repositoryRoot, 'kernel'),
    env: kernelEnvironment(),
  };
}
