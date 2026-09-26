import { describe, expect, it } from 'vitest';

import { DEVIATION_COLORS } from '../viewport/palette';
import {
  NO_DATA_COLOR_INDEX,
  automaticRange,
  bandIndex,
  deviationBands,
  niceCeil,
} from './deviationBands';

describe('deviationBands', () => {
  const bands = deviationBands(0.1, 0.5);

  it('has nine bands with the tolerance band in the middle', () => {
    expect(bands).toHaveLength(9);
    expect(bands[4]).toMatchObject({ from: -0.1, to: 0.1, kind: 'tolerance' });
    expect(bands[4]?.color).toBe(DEVIATION_COLORS.standard[4]);
  });

  it('divides the range into thirds', () => {
    expect(bands[5]?.to).toBeCloseTo(0.5 / 3);
    expect(bands[6]?.to).toBeCloseTo((2 * 0.5) / 3);
    expect(bands[7]?.to).toBeCloseTo(0.5);
  });

  it('assigns values and missing data to bands', () => {
    expect(bandIndex(0, bands)).toBe(4);
    expect(bandIndex(0.3, bands)).toBe(6);
    expect(bandIndex(-0.6, bands)).toBe(0);
    expect(bandIndex(9, bands)).toBe(8);
    expect(bandIndex(Number.NaN, bands)).toBe(NO_DATA_COLOR_INDEX);
  });

  it('uses the colour-blind scheme on request', () => {
    expect(deviationBands(0.1, 0.5, 'colorBlind')[4]?.color).toBe(DEVIATION_COLORS.colorBlind[4]);
  });

  it('rejects a range that does not exceed the tolerance', () => {
    expect(() => deviationBands(0.1, 0.1)).toThrow();
  });
});

describe('scale range', () => {
  it('rounds up to 1, 2 or 5 times a power of ten', () => {
    expect(niceCeil(0.37)).toBe(0.5);
    expect(niceCeil(0.12)).toBeCloseTo(0.2);
    expect(niceCeil(3)).toBe(5);
    expect(niceCeil(1)).toBe(1);
  });

  it('uses the 99th percentile of the absolute deviation', () => {
    const values = new Float32Array(1000).map((_, index) => (index % 2 ? 1 : -1) * index * 0.001);
    expect(automaticRange(values, 0.1)).toBe(1);
  });
});
