// The remote pipeline: rebuild the reference part, a TV remote scan, with the app's
// tools as a user would, measure the result region by region, look at it, and compare
// with the previous run. Every merge is judged on it.
//
//   M2C_REMOTE_SCAN=<path to the scan .stl> M2C_INSTANCE=<name> npm run usertest -- remote
//
// (or `-- remote --scan=<path>`). The scan never goes into the repository. Results:
// test-results/remote/ (report.json, report.md, screenshots).

import { existsSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

import { createDriver } from '../driver.mjs';
import { look, heatmap } from './look.mjs';
import { measure } from './measure/index.mjs';
import { compare, previousReport, table, worst, writeReport } from './report.mjs';
import { REQUIRED, STEPS } from './steps/index.mjs';

const OUT = path.join('test-results', 'remote');

/** The scan's path from `--scan=` or M2C_REMOTE_SCAN, or null. */
export function remoteScanPath(argv = process.argv) {
  const argument = argv.find((value) => value.startsWith('--scan='));
  return argument ? argument.slice('--scan='.length) : (process.env.M2C_REMOTE_SCAN ?? null);
}

function commit() {
  try {
    return execFileSync('git', ['rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim();
  } catch {
    return 'unknown';
  }
}

const message = (error) => (error instanceof Error ? error.message : String(error));

/** Run the build steps in order; a failed step is recorded and the next one tried. */
async function build(ctx, report) {
  for (const step of STEPS) {
    const started = Date.now();
    console.log(`  ${step.id}: ${step.title}`);
    const entry = { id: step.id, title: step.title, ok: false };
    try {
      const result = (await step.run(ctx)) ?? {};
      const { gaps = [], ...details } = result;
      Object.assign(entry, { ok: true, details });
      report.gaps.push(...gaps.map((gap) => `${step.id}: ${gap}`));
    } catch (error) {
      entry.error = message(error);
      report.gaps.push(`${step.id}: failed: ${entry.error}`);
      await ctx.d.shot(`error-${step.id}`).catch(() => undefined);
      await ctx.d.key('Escape').catch(() => undefined);
    }
    entry.seconds = +((Date.now() - started) / 1000).toFixed(1);
    report.steps.push(entry);
    console.log(`    ${entry.ok ? 'ok' : 'FAILED'} (${entry.seconds} s) ${entry.error ?? JSON.stringify(entry.details)}`);
    if (!entry.ok && REQUIRED.has(step.id)) break;
  }
}

export async function remoteTest(d, client) {
  const scanPath = remoteScanPath();
  if (!scanPath) {
    console.log('skipped: set M2C_REMOTE_SCAN (or --scan=<path>) to the remote scan (.stl).');
    return;
  }
  if (!existsSync(scanPath)) {
    d.check('the remote scan exists', false, scanPath);
    return;
  }
  mkdirSync(OUT, { recursive: true });
  const previous = previousReport(OUT);
  const eyes = createDriver(client, path.join(OUT, 'shots'));
  const ctx = { d: eyes, scanPath };
  const report = {
    started: new Date().toISOString(),
    commit: commit(),
    scan: { path: scanPath, triangles: null },
    steps: [],
    gaps: [],
    measure: null,
    heatmapSeconds: null,
    shots: [],
  };

  await eyes.press('recovery-discard').catch(() => undefined);
  await eyes.key('Escape');
  await build(ctx, report);
  report.scan.triangles = ctx.bounds?.faces ?? null;

  if (ctx.bounds) {
    try {
      report.measure = await measure(ctx);
    } catch (error) {
      report.gaps.push(`measure: ${message(error)}`);
    }
    try {
      report.heatmapSeconds = await heatmap(eyes);
      const seen = await look(ctx);
      report.shots = seen.shots;
      report.gaps.push(...seen.problems.map((problem) => `look: ${problem}`));
    } catch (error) {
      report.gaps.push(`look: ${message(error)}`);
    }
  }

  const changes = compare(previous, report);
  writeReport(OUT, report, changes);
  if (report.measure) {
    const { overall } = report.measure;
    console.log(`\n${table(report.measure.regions)}\n`);
    console.log(
      `  all: ${(overall.within * 100).toFixed(1)} % within, RMS ${overall.rms} mm, ` +
        `max ${overall.max?.value} mm at ${overall.max?.at.join(', ')}`,
    );
    console.log(`  worst: ${worst(report.measure.regions).map((region) => region.name).join(', ')}`);
  }
  for (const gap of report.gaps) console.log(`  gap  ${gap}`);
  for (const line of changes) console.log(`  ${line}`);
  console.log(`  report: ${path.join(OUT, 'report.md')}`);

  d.check('the remote is built and measured', report.measure !== null && report.shots.length > 0);
}
