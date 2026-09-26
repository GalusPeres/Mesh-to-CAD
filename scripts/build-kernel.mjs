// Builds the frozen kernel into release/kernel/ (PyInstaller, kernel/m2c-kernel.spec)
// and prepares the other resources the installer bundles: licence texts, example
// scans and help pages. `npm run dist` runs it between the Vite build and
// electron-builder.
//
//   node scripts/build-kernel.mjs [--kernel-only] [--skip-smoke]

import { spawnSync } from 'node:child_process';
import { readdirSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import { runKernelSmoke } from './kernel-smoke.mjs';
import { childEnvironment, pythonExecutable, root } from './paths.mjs';

const KERNEL_DIRECTORY = path.join(root, 'release', 'kernel');
/** Size target of the unpacked kernel (docs/ARCHITECTURE.md 8, item 24). */
const KERNEL_TARGET_MB = 450;

const options = new Set(process.argv.slice(2));

function run(command, args, extraEnv = {}) {
  console.log(`\n> ${path.basename(command)} ${args.join(' ')}`);
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: 'inherit',
    env: childEnvironment({
      PYTHONPATH: path.join(root, 'kernel'),
      PYTHONUTF8: '1',
      ...extraEnv,
    }),
  });
  if (result.status !== 0) {
    throw new Error(`${path.basename(command)} ${args[0]} failed with exit code ${result.status}`);
  }
}

function folderBytes(folder) {
  return readdirSync(folder, { withFileTypes: true }).reduce((sum, entry) => {
    const full = path.join(folder, entry.name);
    return sum + (entry.isDirectory() ? folderBytes(full) : statSync(full).size);
  }, 0);
}

function sizeReport() {
  const internal = path.join(KERNEL_DIRECTORY, '_internal');
  const parts = readdirSync(internal, { withFileTypes: true })
    .map((entry) => {
      const full = path.join(internal, entry.name);
      return {
        name: entry.name,
        bytes: entry.isDirectory() ? folderBytes(full) : statSync(full).size,
      };
    })
    .sort((a, b) => b.bytes - a.bytes);
  const total = folderBytes(KERNEL_DIRECTORY);
  const megabytes = (bytes) => Math.round((bytes / 1024 / 1024) * 10) / 10;
  const report = {
    kernelMB: megabytes(total),
    targetMB: KERNEL_TARGET_MB,
    largest: parts.slice(0, 12).map((part) => ({ name: part.name, mb: megabytes(part.bytes) })),
  };
  writeFileSync(
    path.join(root, 'release', 'kernel-size.json'),
    `${JSON.stringify(report, null, 2)}\n`,
  );
  console.log(`\nKernel size: ${report.kernelMB} MB (target ${KERNEL_TARGET_MB} MB)`);
  for (const part of report.largest)
    console.log(`  ${String(part.mb).padStart(7)} MB  ${part.name}`);
  return report;
}

async function main() {
  const python = pythonExecutable();
  if (!options.has('--kernel-only')) {
    run(python, ['scripts/collect-licenses.py']);
    run(python, ['scripts/generate-examples.py']);
    run(process.execPath, ['scripts/generate-help.mjs']);
  }
  run(python, [
    '-m',
    'PyInstaller',
    'kernel/m2c-kernel.spec',
    '--noconfirm',
    '--clean',
    '--log-level',
    'WARN',
    '--distpath',
    'release',
    '--workpath',
    path.join('release', 'pyinstaller'),
  ]);
  const report = sizeReport();
  if (!options.has('--skip-smoke')) {
    const summary = await runKernelSmoke(path.join(KERNEL_DIRECTORY, 'm2c-kernel.exe'));
    console.log(
      `Kernel smoke test passed (ready after ${summary.readyMs} ms, OCCT ${summary.occtVersion}).`,
    );
  }
  if (report.kernelMB > KERNEL_TARGET_MB) {
    console.warn(
      `The kernel exceeds its size target by ${Math.round(report.kernelMB - KERNEL_TARGET_MB)} MB.`,
    );
  }
}

main().catch((error) => {
  console.error(`\nKernel build failed: ${error.message}`);
  process.exit(1);
});
