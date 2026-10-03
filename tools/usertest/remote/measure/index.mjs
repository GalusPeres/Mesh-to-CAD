// Measure the result like the user reads the heatmap, region by region: the deviation
// of every scan point from the bodies (Prüfen → Abweichung), sorted into the regions of
// regions.mjs, with the share within ±0.1 mm, RMS, the largest deviation and where it
// is, and how much of the scan has no body within the search distance at all.

import { classify } from './regions.mjs';

export const WITHIN_MM = 0.1;
/** Search distance of the deviation: scan farther than this from any body is not covered. */
export const COVER_MM = 2;
/** Typed arrays longer than this come back from the automation interface as a summary. */
const INLINE_VALUES = 2_000_000;

const round = (value, digits = 3) => (Number.isFinite(value) ? +value.toFixed(digits) : null);

/** Statistics of one region from the deviation values of its points (null = not covered). */
function regionStats(values) {
  let covered = 0;
  let within = 0;
  let squares = 0;
  let worst = -1;
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i].value;
    if (value === null) continue;
    covered += 1;
    squares += value * value;
    if (Math.abs(value) <= WITHIN_MM) within += 1;
    if (worst < 0 || Math.abs(value) > Math.abs(values[worst].value)) worst = i;
  }
  const points = values.length;
  const max = worst >= 0 ? values[worst] : null;
  return {
    points,
    within: points ? round(within / points, 4) : null,
    rms: covered ? round(Math.sqrt(squares / covered)) : null,
    max: max && { value: round(max.value), at: max.at.map((v) => round(v, 1)) },
    uncovered: points ? round((points - covered) / points, 4) : null,
  };
}

/**
 * Deviation of the scan from all bodies, per region. Needs the fitted planes
 * (`ctx.planes`); the recognised shapes (`ctx.shapes`) only name the shape regions.
 */
export async function measure(ctx) {
  const { d } = ctx;
  if (!ctx.planes) throw new Error('the regions need the top and bottom planes');
  const started = Date.now();
  const deviation = await d.kernel('inspection.deviation', { bodies: [], maxDistance: COVER_MM });
  if (!Array.isArray(deviation.values)) throw new Error('the deviation came back as a summary');
  const every = Math.ceil((deviation.values.length * 3) / INLINE_VALUES);
  const scan = await d.kernel('automation.scanVertices', { every });
  const { region, regions } = classify(scan.positions, scan.normals, ctx.planes, ctx.shapes);

  const buckets = regions.map(() => []);
  for (let k = 0; k < region.length; k += 1) {
    const value = deviation.values[k * every];
    buckets[region[k]].push({
      value: Number.isFinite(value) ? value : null,
      at: [scan.positions[k * 3], scan.positions[k * 3 + 1], scan.positions[k * 3 + 2]],
    });
  }
  const all = regionStats(buckets.flat());
  return {
    seconds: +((Date.now() - started) / 1000).toFixed(1),
    sampled: every,
    stats: deviation.stats,
    overall: all,
    regions: regions
      .map((item, index) => ({ ...item, ...regionStats(buckets[index]) }))
      .filter((item) => item.points > 0),
  };
}
