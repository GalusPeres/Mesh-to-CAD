// The pipeline's report: report.json (read by the next run), a short table on the
// console and report.md with the same table for a pull request, plus what got better
// or worse per region since the previous run.

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import { WITHIN_MM } from './measure/index.mjs';

/** Changes smaller than these are noise between runs. */
const NOTICE = { within: 0.01, rms: 0.005, max: 0.05, uncovered: 0.01 };
const SAME_SHAPE_MM = 2;

const percent = (share) => (share === null ? '–' : `${(share * 100).toFixed(1)} %`);
const mm = (value) => (value === null || value === undefined ? '–' : value.toFixed(3));
const at = (max) => (max ? `${max.at.join(', ')}` : '–');

function rows(regions) {
  return regions.map((region) => [
    region.name,
    String(region.points),
    percent(region.within),
    mm(region.rms),
    mm(region.max?.value),
    at(region.max),
    percent(region.uncovered),
  ]);
}

const HEADER = [
  'Region',
  'Points',
  `±${WITHIN_MM} mm`,
  'RMS',
  'Max',
  'Max at (x, y, z)',
  'Not covered',
];

/** The regions as a fixed-width console table. */
export function table(regions) {
  const body = rows(regions);
  const widths = HEADER.map((title, column) =>
    Math.max(title.length, ...body.map((row) => row[column].length)),
  );
  const line = (cells) =>
    cells
      .map((cell, column) => (column === 0 ? cell.padEnd(widths[0]) : cell.padStart(widths[column])))
      .join('  ');
  return [line(HEADER), ...body.map(line)].join('\n');
}

/** The regions as a Markdown table. */
export function markdownTable(regions) {
  const line = (cells) => `| ${cells.join(' | ')} |`;
  return [line(HEADER), line(HEADER.map(() => '---')), ...rows(regions).map(line)].join('\n');
}

/** The regions that fit worst: the lowest share within the tolerance first. */
export function worst(regions, count = 3) {
  return [...regions]
    .filter((region) => region.points >= 100)
    .sort((a, b) => (a.within ?? 0) - (b.within ?? 0) || (b.rms ?? 0) - (a.rms ?? 0))
    .slice(0, count);
}

/** What changed per region since `previous`: lines starting with "better" or "worse". */
export function compare(previous, current) {
  if (!previous?.measure) return [];
  const before = new Map(previous.measure.regions.map((region) => [region.name, region]));
  // Shapes are the same shape when their centres are close, even if a name changed.
  const same = (region) =>
    before.get(region.name) ??
    previous.measure.regions.find(
      (old) => old.centre && region.centre && Math.hypot(old.centre[0] - region.centre[0], old.centre[1] - region.centre[1]) < SAME_SHAPE_MM,
    );
  const matched = new Set();
  const lines = [];
  for (const region of current.measure.regions) {
    const old = same(region);
    if (old) matched.add(old.name);
    if (!old) {
      lines.push(`new     ${region.name}`);
      continue;
    }
    const changes = [];
    const note = (label, delta, limit, higherIsBetter, format) => {
      if (delta === null || Math.abs(delta) < limit) return;
      changes.push({ better: higherIsBetter ? delta > 0 : delta < 0, text: format(delta) });
    };
    const diff = (a, b) => (a === null || b === null ? null : a - b);
    const sign = (value, text) => `${value > 0 ? '+' : ''}${text}`;
    note('within', diff(region.within, old.within), NOTICE.within, true, (v) =>
      sign(v, `${(v * 100).toFixed(1)} pt within`),
    );
    note('rms', diff(region.rms, old.rms), NOTICE.rms, false, (v) => sign(v, `${v.toFixed(3)} RMS`));
    const max = diff(Math.abs(region.max?.value ?? 0), Math.abs(old.max?.value ?? 0));
    note('max', max, NOTICE.max, false, (v) => sign(v, `${v.toFixed(3)} max`));
    note('uncovered', diff(region.uncovered, old.uncovered), NOTICE.uncovered, false, (v) =>
      sign(v, `${(v * 100).toFixed(1)} pt not covered`),
    );
    for (const better of [true, false]) {
      const chosen = changes.filter((change) => change.better === better);
      if (chosen.length) {
        lines.push(`${better ? 'better' : 'worse '}  ${region.name}: ${chosen.map((c) => c.text).join(', ')}`);
      }
    }
  }
  for (const name of before.keys()) if (!matched.has(name)) lines.push(`gone    ${name}`);
  return lines;
}

/** The previous run's report from `dir`, or null. */
export function previousReport(dir) {
  const file = path.join(dir, 'report.json');
  if (!existsSync(file)) return null;
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

/** Write report.json, a dated copy and report.md into `dir`. */
export function writeReport(dir, report, changes) {
  const json = JSON.stringify(report, null, 2);
  writeFileSync(path.join(dir, 'report.json'), json);
  writeFileSync(path.join(dir, `report-${report.started.replace(/[:.]/g, '-')}.json`), json);
  const steps = report.steps.map(
    (step) =>
      `- ${step.ok ? 'ok' : 'FAILED'} **${step.id}** (${step.seconds} s)` +
      (step.error ? `: ${step.error}` : ''),
  );
  const gaps = report.gaps.map((gap) => `- ${gap}`);
  const markdown = [
    `# Remote pipeline, ${report.started}`,
    '',
    `Commit ${report.commit}, scan ${report.scan.triangles} triangles.`,
    '',
    '## Steps',
    ...steps,
    '',
    '## Gaps',
    ...(gaps.length ? gaps : ['- none']),
    '',
    '## Regions',
    report.measure ? markdownTable(report.measure.regions) : '_not measured_',
    '',
    '## Since the previous run',
    ...(changes.length ? changes.map((line) => `- ${line}`) : ['- no previous run or no change']),
    '',
  ].join('\n');
  writeFileSync(path.join(dir, 'report.md'), markdown);
}
