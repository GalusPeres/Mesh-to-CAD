import { describe, expect, it } from 'vitest';

import { createFormatter } from '../i18n/format';
import { bandIndex, deviationBands } from '../lib/deviationBands';
import { DEVIATION_COLORS } from '../viewport/palette';
import {
  automaticScaleRange,
  cursorLabel,
  effectiveRange,
  isValidRange,
  legendLayout,
  minimumRange,
  tickDecimals,
} from './deviationModel';

const de = createFormatter('de-DE');
const en = createFormatter('en-US');

describe('legend layout', () => {
  it('matches the legend of DESIGN.md 6.6 in German', () => {
    const layout = legendLayout(0.1, 0.5, 'standard', de);
    expect(layout.ticks).toEqual([
      '+0,50',
      '+0,33',
      '+0,17',
      '+0,10',
      '−0,10',
      '−0,17',
      '−0,33',
      '−0,50',
    ]);
  });

  it('uses English separators in English', () => {
    expect(legendLayout(0.1, 0.5, 'standard', en).ticks).toEqual([
      '+0.50',
      '+0.33',
      '+0.17',
      '+0.10',
      '−0.10',
      '−0.17',
      '−0.33',
      '−0.50',
    ]);
  });

  it('draws positive values at the top and the tolerance band twice as high', () => {
    const layout = legendLayout(0.1, 0.5, 'standard', de);
    const colors = DEVIATION_COLORS.standard;
    expect(layout.bands.map((band) => band.color)).toEqual(colors.slice(1, 8).reverse());
    expect(layout.bands.map((band) => band.weight)).toEqual([1, 1, 1, 2, 1, 1, 1]);
    expect(layout.bands[3]?.tolerance).toBe(true);
    expect([layout.above, layout.below, layout.noData]).toEqual([colors[8], colors[0], colors[9]]);
  });

  it('switches every colour for the colour-blind scheme', () => {
    const layout = legendLayout(0.1, 0.5, 'colorBlind', de);
    const colors = DEVIATION_COLORS.colorBlind;
    expect(layout.bands.map((band) => band.color)).toEqual(colors.slice(1, 8).reverse());
    expect(layout.bands[3]?.color).toBe(colors[4]);
    expect(layout.noData).toBe(colors[9]);
  });

  it('shows three decimals where two would repeat a tick', () => {
    expect(tickDecimals(0.1, 0.5)).toBe(2);
    expect(tickDecimals(0.005, 0.02)).toBe(3);
    expect(legendLayout(0.005, 0.02, 'standard', de).ticks.slice(0, 4)).toEqual([
      '+0,020',
      '+0,013',
      '+0,007',
      '+0,005',
    ]);
  });
});

describe('scale range', () => {
  it('never lets the steps overlap the tolerance band', () => {
    expect(minimumRange(0.1)).toBeCloseTo(0.3);
    expect(effectiveRange('auto', null, 0.2, 0.1)).toBe(0.5);
    expect(effectiveRange('auto', null, 1, 0.1)).toBe(1);
    const bands = deviationBands(0.1, effectiveRange('auto', null, 0.2, 0.1));
    expect(bandIndex(0.08, bands)).toBe(4);
    expect(bandIndex(-0.08, bands)).toBe(4);
  });

  it('uses a manual range only above three tolerances', () => {
    expect(isValidRange(0.3, 0.1)).toBe(false);
    expect(isValidRange(0.4, 0.1)).toBe(true);
    expect(effectiveRange('manual', 0.4, 1, 0.1)).toBe(0.4);
    expect(effectiveRange('manual', 0.2, 1, 0.1)).toBe(1);
    expect(effectiveRange('manual', null, 1, 0.1)).toBe(1);
  });

  it('takes the 99th percentile of |d| on a sample of large maps', () => {
    const values = new Float32Array(1_000_000).map((_, index) =>
      index % 1000 === 0 ? Number.NaN : ((index % 2 ? 1 : -1) * (index % 1000)) / 1000,
    );
    expect(automaticScaleRange(values, 0.1)).toBe(1);
    expect(automaticScaleRange(new Float32Array(100).fill(0.01), 0.1)).toBe(0.5);
  });
});

describe('cursor value', () => {
  it('is signed with three decimals, or no data', () => {
    expect(cursorLabel(0.0412, de)).toBe('+0,041 mm');
    expect(cursorLabel(-0.2, en)).toBe('−0.200 mm');
    expect(cursorLabel(Number.NaN, de)).toBeNull();
    expect(cursorLabel(undefined, de)).toBeNull();
  });
});
