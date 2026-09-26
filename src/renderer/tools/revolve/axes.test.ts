import { describe, expect, it } from 'vitest';

import type { RevolveAxis } from '@shared/protocol/generated/feature-revolve';

import { axisKey, parseAxisKey, sketchLines } from './axes';

describe('revolve axes', () => {
  it('round-trips every axis kind through the select value', () => {
    const axes: RevolveAxis[] = [
      { type: 'globalAxis', axis: 'Z' },
      { type: 'featureAxis', feature: 'f4' },
      { type: 'sketchLine', entity: 'e12' },
    ];
    for (const axis of axes) expect(parseAxisKey(axisKey(axis))).toEqual(axis);
  });

  it('rejects malformed values', () => {
    expect(parseAxisKey('global:W')).toBeNull();
    expect(parseAxisKey('feature:')).toBeNull();
    expect(parseAxisKey('nothing')).toBeNull();
  });

  it('lists the line entities of a sketch', () => {
    const sketch = {
      params: {
        entities: [
          { type: 'line', id: 'e1' },
          { type: 'arc', id: 'e2' },
          { type: 'line', id: 'e3' },
          { type: 'circle', id: 'e4' },
        ],
      },
    };
    expect(sketchLines(sketch)).toEqual(['e1', 'e3']);
    expect(sketchLines(undefined)).toEqual([]);
    expect(sketchLines({ params: null })).toEqual([]);
  });
});
