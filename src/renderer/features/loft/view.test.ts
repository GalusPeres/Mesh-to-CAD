import i18next, { type TFunction } from 'i18next';
import { beforeAll, describe, expect, it } from 'vitest';

import type { FeatureTypes } from '@shared/protocol/generated/index';

import { createFormatter } from '../../i18n/format';
import { buildResources } from '../../i18n/resources';
import { featureView as loft } from './view';

const format = createFormatter('de-DE');
let t: TFunction;

beforeAll(async () => {
  const instance = i18next.createInstance();
  await instance.init({
    resources: buildResources(),
    lng: 'de',
    interpolation: { escapeValue: false },
  });
  t = instance.t;
});

const params = (
  overrides: Partial<FeatureTypes['loft']['params']>,
): FeatureTypes['loft']['params'] => ({
  path: 'Z',
  start: 0.5,
  end: 19.5,
  sectionCount: 12,
  faces: null,
  operation: 'newBody',
  targetBody: null,
  startPlane: null,
  endPlane: null,
  ...overrides,
});

describe('loft summary (German)', () => {
  it('names axis, sections and range', () => {
    expect(loft.summary!(params({}), format, t)).toBe('Z: 12 Schnitte über 19,000 mm');
  });

  it('says when an end reaches a plane', () => {
    expect(loft.summary!(params({ startPlane: 'XY', endPlane: 'f2' }), format, t)).toBe(
      'Z: 12 Schnitte über 19,000 mm, bis Ebene',
    );
    expect(loft.summary!(params({ endPlane: 'f2' }), format, t)).toBe(
      'Z: 12 Schnitte über 19,000 mm, bis Ebene',
    );
  });
});
