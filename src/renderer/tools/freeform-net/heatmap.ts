// Deviation colours and statistics of the net's surface against the scan. The bands
// are the app's deviation bands (lib/deviationBands.ts), so the colours mean the same
// as on the scan's deviation map: green within the tolerance, warm colours where the
// surface lies outside the material, cool colours where it lies inside.

import { Color } from 'three';

import { NO_DATA_COLOR_INDEX, deviationBands } from '../../lib/deviationBands';
import { DEVIATION_COLORS, type DeviationScheme, SCENE_COLORS } from '../../viewport/palette';

/** The colour gradient ends at this multiple of the tolerance. */
export const RANGE_FACTOR = 5;
/** Colour scales the panel offers (mm); the default is the first one at or above the project tolerance. */
export const HEATMAP_TOLERANCES = [0.05, 0.1, 0.2, 0.5] as const;

export function defaultHeatmapTolerance(projectTolerance: number): number {
  return HEATMAP_TOLERANCES.find((value) => value >= Math.max(projectTolerance, 0.1)) ?? 0.5;
}
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

/** Linear RGB of band `index` of the scale. */
function bandColor(scale: HeatmapScale, index: number): [number, number, number] {
  const o = index * 3;
  return [scale.colors[o] ?? 0, scale.colors[o + 1] ?? 0, scale.colors[o + 2] ?? 0];
}

/**
 * Colour of a signed distance: the tolerance colour up to the tolerance, then a
 * smooth gradient through the warm steps (outside the material) or the cool steps
 * (inside) that ends at the range; beyond it the out-of-range colour. A gradient
 * reads like a map of the surface; hard bands would draw contour lines into it.
 */
function colorOf(value: number, scale: HeatmapScale): [number, number, number] {
  if (Number.isNaN(value)) return bandColor(scale, NO_DATA_COLOR_INDEX);
  const magnitude = Math.abs(value);
  if (magnitude <= scale.tolerance) return bandColor(scale, 4);
  if (magnitude >= scale.range) return bandColor(scale, value > 0 ? 8 : 0);
  // Stops from the tolerance to the range: three steps of the palette on each side.
  const stops = value > 0 ? [5, 6, 7] : [3, 2, 1];
  const t = ((magnitude - scale.tolerance) / (scale.range - scale.tolerance)) * (stops.length - 1);
  const low = Math.floor(t);
  const high = Math.min(stops.length - 1, low + 1);
  const a = bandColor(scale, stops[low] ?? 4);
  const b = bandColor(scale, stops[high] ?? 4);
  const f = t - low;
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** Write the colour of every distance (or of `indices` only) into `out` (RGB). */
export function colorize(
  distances: Float32Array,
  scale: HeatmapScale,
  out: Float32Array,
  indices?: Uint32Array,
): void {
  const paint = (i: number) => {
    out.set(colorOf(distances[i] ?? Number.NaN, scale), i * 3);
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
