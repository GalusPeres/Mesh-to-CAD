// Band layout of the deviation colour map (docs/DESIGN.md 6.6), shared by the
// legend and the viewport's colour texture so both always agree.

import { DEVIATION_COLORS, type DeviationScheme } from '../viewport/palette';

export interface DeviationBand {
  /** Lower bound in mm (-Infinity for the lowest band). */
  from: number;
  /** Upper bound in mm (+Infinity for the highest band). */
  to: number;
  color: string;
  kind: 'belowRange' | 'negative' | 'tolerance' | 'positive' | 'aboveRange';
}

export const NO_DATA_COLOR_INDEX = 9;
const STEPS_PER_SIDE = 3;

/**
 * Nine bands: out of range, three negative steps from -range to -tolerance, the
 * tolerance band, three positive steps, out of range. Step boundaries divide the
 * range into thirds, as in the design specification.
 */
export function deviationBands(
  tolerance: number,
  range: number,
  scheme: DeviationScheme = 'standard',
): DeviationBand[] {
  if (!(tolerance > 0) || !(range > tolerance)) {
    throw new Error(`invalid deviation scale: tolerance ${tolerance}, range ${range}`);
  }
  const colors = DEVIATION_COLORS[scheme];
  const color = (index: number) => colors[index] ?? colors[NO_DATA_COLOR_INDEX] ?? '';
  const third = range / STEPS_PER_SIDE;
  const edges = [range, 2 * third, third];
  const bands: DeviationBand[] = [
    { from: -Infinity, to: -range, color: color(0), kind: 'belowRange' },
  ];
  bands.push({ from: -edges[0]!, to: -edges[1]!, color: color(1), kind: 'negative' });
  bands.push({ from: -edges[1]!, to: -edges[2]!, color: color(2), kind: 'negative' });
  bands.push({ from: -edges[2]!, to: -tolerance, color: color(3), kind: 'negative' });
  bands.push({ from: -tolerance, to: tolerance, color: color(4), kind: 'tolerance' });
  bands.push({ from: tolerance, to: edges[2]!, color: color(5), kind: 'positive' });
  bands.push({ from: edges[2]!, to: edges[1]!, color: color(6), kind: 'positive' });
  bands.push({ from: edges[1]!, to: edges[0]!, color: color(7), kind: 'positive' });
  bands.push({ from: range, to: Infinity, color: color(8), kind: 'aboveRange' });
  return bands;
}

/** Index of the band containing `value`; NaN (no data) gives `NO_DATA_COLOR_INDEX`. */
export function bandIndex(value: number, bands: readonly DeviationBand[]): number {
  if (Number.isNaN(value)) return NO_DATA_COLOR_INDEX;
  const index = bands.findIndex((band) => value >= band.from && value < band.to);
  return index === -1 ? bands.length - 1 : index;
}

/** Scale range "automatic": the 99th percentile of |d|, rounded up to 1, 2 or 5 x 10^n. */
export function automaticRange(values: Float32Array, tolerance: number): number {
  const magnitudes = Array.from(values, Math.abs).filter((value) => Number.isFinite(value));
  if (magnitudes.length === 0) return tolerance * 3;
  magnitudes.sort((a, b) => a - b);
  const p99 =
    magnitudes[Math.min(magnitudes.length - 1, Math.floor(magnitudes.length * 0.99))] ?? 0;
  return Math.max(niceCeil(p99), niceCeil(tolerance * 1.5));
}

export function niceCeil(value: number): number {
  if (!(value > 0)) return 0;
  const exponent = Math.floor(Math.log10(value));
  for (const step of [1, 2, 5, 10]) {
    const candidate = step * 10 ** exponent;
    if (candidate >= value * (1 - 1e-12)) return candidate;
  }
  return 10 ** (exponent + 1);
}
