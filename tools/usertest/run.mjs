#!/usr/bin/env node
// User tests: drive a running development app like a user would, on a synthetic part,
// check the numbers and save screenshots to look at (AGENTS.md, "Done means").
//
//   M2C_INSTANCE=<name> M2C_WINDOW=offscreen M2C_AUTOMATION=1 npm run dev
//   M2C_INSTANCE=<name> npm run usertest [-- <test> ...]
//
// `remote` (the reference part rebuilt end to end, tools/usertest/remote/) runs only
// when named, on the scan given by M2C_REMOTE_SCAN or --scan=<path>.
//
// They run only against an app of its own (M2C_INSTANCE), never the user's: each run
// starts a new project there. Screenshots: test-results/usertest/<instance>/.

import { mkdtempSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { INSTANCE, automationClient } from '../automation/client.mjs';
import { writeBlockPart } from './block.mjs';
import { createDriver } from './driver.mjs';
import { hideTest } from './hide.mjs';
import { loftTest } from './loft.mjs';
import { loftEndTest } from './loftend.mjs';
import { netTest } from './net.mjs';
import { writeButtonsPart, writeTestPart } from './part.mjs';
import { recognizeTest } from './recognize.mjs';
import { remoteTest } from './remote/index.mjs';
import { writeRoundedBlock } from './rounded.mjs';
import { roundingTest } from './rounding.mjs';
import { sketchTest } from './sketch.mjs';
import { solidTest } from './solid.mjs';
import { writeTubPart } from './tub.mjs';

/** Every user test by name; add one per tool. */
const TESTS = {
  net: netTest,
  loft: loftTest,
  loftend: loftEndTest,
  recognize: recognizeTest,
  sketch: sketchTest,
  hide: hideTest,
  solid: solidTest,
  rounding: roundingTest,
};

/** Long tests on a real scan, run only when named; they start their project themselves. */
const ON_REQUEST = { remote: remoteTest };

/** The part a test runs on, when it is not the plate with the boss. */
const PARTS = {
  recognize: writeButtonsPart,
  solid: writeTubPart,
  rounding: writeBlockPart,
  loftend: writeRoundedBlock,
};

/** A new project with a synthetic part as its scan, no tool open. */
async function startOver(client, d, writePart) {
  await d.key('Escape');
  await client.kernel('project.new');
  const file = path.join(mkdtempSync(path.join(os.tmpdir(), 'm2c-usertest-')), 'part.stl');
  writePart(file);
  const pending = await client.kernel('mesh.import', { path: file });
  await client.kernel('mesh.commitImport', {
    pendingId: pending.pendingId,
    unit: 'mm',
    reduceTo: null,
  });
  await d.until(
    async () => (await client.ui({ type: 'state' }))?.revision > 0,
    'the imported scan',
  );
}

async function main() {
  if (!INSTANCE) {
    console.error('Set M2C_INSTANCE to the name of your own app (see the header of this file).');
    process.exit(2);
  }
  const named = process.argv.slice(2).filter((argument) => !argument.startsWith('--'));
  const names = named.length > 0 ? named : Object.keys(TESTS);
  const known = { ...TESTS, ...ON_REQUEST };
  const unknown = names.filter((name) => !known[name]);
  if (unknown.length > 0) {
    console.error(`Unknown test: ${unknown.join(', ')}. Known: ${Object.keys(known).join(', ')}`);
    process.exit(2);
  }
  const client = automationClient();
  const d = createDriver(client, path.join('test-results', 'usertest', INSTANCE));
  for (const name of names) {
    console.log(`\n== ${name}`);
    try {
      if (ON_REQUEST[name]) {
        await ON_REQUEST[name](d, client);
        continue;
      }
      await startOver(client, d, PARTS[name] ?? writeTestPart);
      await TESTS[name](d);
    } catch (error) {
      d.check(`${name} ran to the end`, false, error instanceof Error ? error.message : error);
      await d.shot(`${name}-error`).catch(() => undefined);
    }
  }
  console.log(d.failures.length === 0 ? '\nAll checks passed.' : `\n${d.failures.length} failed.`);
  process.exit(d.failures.length === 0 ? 0 : 1);
}

await main();
