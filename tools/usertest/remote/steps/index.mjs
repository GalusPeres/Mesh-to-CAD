// The remote's build steps in order. Each step is { id, title, run(ctx) }: it uses the
// app like a user, may leave results for later steps on `ctx` (bounds, planes, body,
// shapes) and returns what it did; `gaps` in its result are tools that are missing or
// broken but were worked around. A better tool replaces only its own step here.

import { baseLoft } from './baseLoft.mjs';
import { baseNet } from './baseNet.mjs';
import { importScan } from './importScan.mjs';
import { planes } from './planes.mjs';
import { recognizeButtons } from './recognizeButtons.mjs';
import { topFillet } from './topFillet.mjs';

/** Ways to build the base body; M2C_REMOTE_BASE picks one (default: the net). */
export const BASES = { net: baseNet, loft: baseLoft };

/** The steps with the base body chosen by `base`. */
export function steps(base = 'net') {
  const chosen = BASES[base];
  if (!chosen) throw new Error(`unknown base body "${base}"; known: ${Object.keys(BASES)}`);
  return [importScan, planes, chosen, topFillet, recognizeButtons];
}

/** Steps that later steps cannot do without: when one fails, the build stops there. */
export const REQUIRED = new Set(['import', 'base']);
