import i18next, { type TFunction } from 'i18next';
import { beforeAll, describe, expect, it } from 'vitest';

import type { FeatureTypes } from '@shared/protocol/generated/index';

import { createFormatter } from '../../i18n/format';
import { buildResources } from '../../i18n/resources';
import { featureView as combine } from '../combine/view';
import { featureView as fillet } from '../fillet/view';
import { featureView as primitiveBody } from '../primitive-body/view';
import { featureView as revolve } from '../revolve/view';
import { featureView as extrude } from './view';

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

type Params<T extends keyof FeatureTypes> = FeatureTypes[T]['params'];

const extrusion = (overrides: Partial<Params<'extrude'>>): Params<'extrude'> => ({
  sketch: 'f1',
  loops: null,
  direction: 'normal',
  extent: { type: 'distance', forward: 12, backward: 0 },
  operation: 'newBody',
  targetBody: null,
  ...overrides,
});

describe('solid feature summaries (German)', () => {
  it('names distance and operation of an extrusion', () => {
    expect(extrude.summary!(extrusion({}), format, t)).toBe('12,000 mm');
    expect(extrude.summary!(extrusion({ operation: 'cut', targetBody: 'f2' }), format, t)).toBe(
      '12,000 mm, Abziehen',
    );
    const both = extrusion({ extent: { type: 'distance', forward: 10, backward: 5 } });
    expect(extrude.summary!(both, format, t)).toBe('10,000 mm / 5,000 mm');
    const toPlane = extrusion({ extent: { type: 'toPlane', feature: 'XY', offset: 0 } });
    expect(extrude.summary!(toPlane, format, t)).toBe('bis Ebene');
  });

  it('summarises revolve, primitive body, combine and fillet', () => {
    const angle: Params<'revolve'> = {
      sketch: 'f1',
      loops: null,
      axis: { type: 'globalAxis', axis: 'Z' },
      angleDeg: 90,
      operation: 'add',
      targetBody: 'f2',
    };
    expect(revolve.summary!(angle, format, t)).toBe('90,00°, Vereinigen');
    const body: Params<'primitiveBody'> = {
      fit: 'f3',
      extent: { type: 'region', margin: 1 },
      operation: 'newBody',
      targetBody: null,
    };
    expect(primitiveBody.summary!(body, format, t)).toBe('Länge aus Scan + 1,000 mm');
    const tools: Params<'combine'> = {
      targetBody: 'f2',
      tools: ['f4', 'f5'],
      operation: 'cut',
      keepTools: false,
    };
    expect(combine.summary!(tools, format, t)).toBe('Abziehen, 2 Werkzeugkörper');
    const rounding: Params<'fillet'> = {
      targetBody: 'f2',
      edges: [{ faces: ['a', 'b'], point: [0, 0, 0] }],
      mode: 'chamfer',
      size: 1.5,
    };
    expect(fillet.summary!(rounding, format, t)).toBe('1,500 mm, 1 Kante');
    expect(fillet.baseName!(rounding, t)).toBe('Fase');
  });
});
