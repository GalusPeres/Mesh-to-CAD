// Deviation colours and statistics of the net's surface against the scan. The bands
// are the app's deviation bands (lib/deviationBands.ts), so the colours mean the same
// as on the scan's deviation map: green within the tolerance, warm colours where the
// surface lies outside the material, cool colours where it lies inside.

import { Color } from 'three';

import { NO_DATA_COLOR_INDEX, bandIndex, deviationBands } from '../../lib/deviationBands';
import { DEVIATION_COLORS, type DeviationScheme, SCENE_COLORS } from '../../viewport/palette';

/** Signed distances beyond this multiple of the tolerance count as "far" (grey). */
export const RANGE_FACTOR = 5;
/** Distances are searched up to this multiple of the range; beyond is no data. */
export const SEARCH_FACTOR = 4;

export interface HeatmapScale {
  tolerance: number;
  range: number;
  /** Linear RGB per band (9 bands, then no data). */
  colors: Float32Array;
  bands: ReturnType<typeof deviationBands>;
}

export function heatmapScale(
  tolerance: number,
  scheme: DeviationScheme = 'standard',
): HeatmapScale {
  const safeTolerance = tolerance > 0 ? tolerance : 0.1;
  const range = safeTolerance * RANGE_FACTOR;
  const bands = deviationBands(safeTolerance, range, scheme);
  const colors = new Float32Array((NO_DATA_COLOR_INDEX + 1) * 3);
  const color = new Color();
  bands.forEach((band, index) => {
    color.set(band.color);
    colors.set([color.r, color.g, color.b], index * 3);
  });
  color.set(DEVIATION_COLORS[scheme][NO_DATA_COLOR_INDEX] ?? SCENE_COLORS.scan);
  colors.set([color.r, color.g, color.b], NO_DATA_COLOR_INDEX * 3);
  return { tolerance: safeTolerance, range, colors, bands };
}

/** No-data colour: the grey of the deviation palette. */
export function noDataColor(scale: HeatmapScale): [number, number, number] {
  const o = NO_DATA_COLOR_INDEX * 3;
  return [scale.colors[o] ?? 0.5, scale.colors[o + 1] ?? 0.5, scale.colors[o + 2] ?? 0.5];
}

/** Write the band colour of every distance (or of `indices` only) into `out` (RGB). */
export function colorize(
  distances: Float32Array,
  scale: HeatmapScale,
  out: Float32Array,
  indices?: Uint32Array,
): void {
  const paint = (i: number) => {
    const value = distances[i] ?? Number.NaN;
    const band = Number.isNaN(value) ? NO_DATA_COLOR_INDEX : bandIndex(value, scale.bands);
    const o = band * 3;
    out[i * 3] = scale.colors[o] ?? 0;
    out[i * 3 + 1] = scale.colors[o + 1] ?? 0;
    out[i * 3 + 2] = scale.colors[o + 2] ?? 0;
  };
  if (indices) for (const i of indices) paint(i);
  else for (let i = 0; i < distances.length; i += 1) paint(i);
}

export interface DeviationSummary {
  /** Number of measured surface points (others are farther than the search distance). */
  measured: number;
  total: number;
  rms: number | null;
  p95: number | null;
  max: number | null;
  /** Share of measured points within the tolerance (0..1). */
  withinTolerance: number | null;
}

/** Statistics of the absolute distances; NaN entries are not measured. */
export function deviationSummary(
  distances: Float32Array,
  tolerance: number,
  skip?: Uint8Array,
): DeviationSummary {
  const values: number[] = [];
  let sumSquares = 0;
  let within = 0;
  for (let i = 0; i < distances.length; i += 1) {
    if (skip && skip[i]) continue;
    const value = Math.abs(distances[i] ?? Number.NaN);
    if (Number.isNaN(value)) continue;
    values.push(value);
    sumSquares += value * value;
    if (value <= tolerance) within += 1;
  }
  const total = skip
    ? distances.length - skip.reduce((sum, flag) => sum + (flag ? 1 : 0), 0)
    : distances.length;
  if (values.length === 0) {
    return { measured: 0, total, rms: null, p95: null, max: null, withinTolerance: null };
  }
  values.sort((a, b) => a - b);
  return {
    measured: values.length,
    total,
    rms: Math.sqrt(sumSquares / values.length),
    p95: values[Math.min(values.length - 1, Math.floor(values.length * 0.95))] ?? null,
    max: values[values.length - 1] ?? null,
    withinTolerance: within / values.length,
  };
}
