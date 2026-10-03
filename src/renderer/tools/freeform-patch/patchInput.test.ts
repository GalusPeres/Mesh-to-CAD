import { describe, expect, it } from 'vitest';

import { SMOOTHING_LEVELS, clampSpans, smoothingLevel } from './patchInput';

describe('freeform patch parameters', () => {
  it('maps stored smoothing weights to the nearest offered level', () => {
    expect(smoothingLevel(SMOOTHING_LEVELS.low)).toBe('low');
    expect(smoothingLevel(1e-4)).toBe('medium');
    expect(smoothingLevel(5e-3)).toBe('high');
    expect(smoothingLevel(0)).toBe('low');
  });

  it('keeps span counts inside the kernel limits', () => {
    expect(clampSpans(1)).toBe(2);
    expect(clampSpans(16.4)).toBe(16);
    expect(clampSpans(500)).toBe(64);
  });
});
