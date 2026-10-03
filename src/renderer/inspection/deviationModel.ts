// Scale range and legend layout of the deviation colour map (docs/DESIGN.md 6.6).
// The band boundaries come from lib/deviationBands.ts, the colours from the palette.

import type { Formatter } from '../i18n/format';
import {
  NO_DATA_COLOR_INDEX,
  automaticRange,
  deviationBands,
  niceCeil,
} from '../lib/deviationBands';
import { DEVIATION_COLORS, type DeviationScheme } from '../viewport/palette';

export type RangeMode = 'auto' | 'manual';

/** Values used for the automatic range; a strided sample keeps the sort cheap on 2 M vertices. */
const AUTO_RANGE_SAMPLE = 100_000;

/**
 * The steps divide the range into thirds, and the first step starts at the tolerance,
 * so the range must exceed three tolerances or the bands would overlap.
 */
export function minimumRange(tolerance: number): number {
  return 3 * tolerance;
}

/** The smallest nice range (1, 2 or 5 x 10^n) above three tolerances. */
function smallestRange(tolerance: number): number {
  return niceCeil(minimumRange(tolerance) * 1.0001);
}

export function automaticScaleRange(values: Float32Array, tolerance: number): number {
  const stride = Math.max(1, Math.floor(values.length / AUTO_RANGE_SAMPLE));
  const sample = stride === 1 ? values : values.filter((_, index) => index % stride === 0);
  return Math.max(automaticRange(sample, tolerance), smallestRange(tolerance));
}

export function isValidRange(range: number | null, tolerance: number): range is number {
  return range !== null && Number.isFinite(range) && range > minimumRange(tolerance);
}

export function effectiveRange(
  mode: RangeMode,
  manual: number | null,
  automatic: number,
  tolerance: number,
): number {
  if (mode === 'manual' && isValidRange(manual, tolerance)) return manual;
  return automatic > minimumRange(tolerance) ? automatic : smallestRange(tolerance);
}

/** Two decimals where they keep every tick distinct, three for small tolerances. */
export function tickDecimals(tolerance: number, range: number): number {
  const magnitudes = [range, (2 * range) / 3, range / 3, tolerance];
  const labels = magnitudes.map((value) => value.toFixed(2));
  return new Set(labels).size === labels.length && Number(labels[3]) !== 0 ? 2 : 3;
}

export function signedNumber(value: number, decimals: number, format: Formatter): string {
  const text = format.number(value, decimals);
  return value > 0 && Number(value.toFixed(decimals)) !== 0 ? `+${text}` : text;
}

export interface LegendBand {
  color: string;
  /** Relative height in the bar; the tolerance band is twice as high as a step. */
  weight: number;
  tolerance: boolean;
}

export interface LegendLayout {
  /** Top to bottom: three positive steps, the tolerance band, three negative steps. */
  bands: LegendBand[];
  /** Labels of the eight band boundaries, top to bottom, sign always shown. */
  ticks: string[];
  decimals: number;
  above: string;
  below: string;
  noData: string;
}

export function legendLayout(
  tolerance: number,
  range: number,
  scheme: DeviationScheme,
  format: Formatter,
): LegendLayout {
  const bands = deviationBands(tolerance, range, scheme);
  const inRange = bands.slice(1, 8).reverse();
  const decimals = tickDecimals(tolerance, range);
  const ticks = [
    ...inRange.slice(0, 4).map((band) => band.to),
    ...inRange.slice(3).map((band) => band.from),
  ];
  return {
    bands: inRange.map((band) => ({
      color: band.color,
      weight: band.kind === 'tolerance' ? 2 : 1,
      tolerance: band.kind === 'tolerance',
    })),
    ticks: ticks.map((value) => signedNumber(value, decimals, format)),
    decimals,
    above: bands[8]?.color ?? '',
    below: bands[0]?.color ?? '',
    noData: DEVIATION_COLORS[scheme][NO_DATA_COLOR_INDEX] ?? '',
  };
}

/** The value under the cursor: signed, three decimals and unit; null for "no data". */
export function cursorLabel(value: number | undefined, format: Formatter): string | null {
  if (value === undefined || Number.isNaN(value)) return null;
  return format.length(value, { signed: true });
}
