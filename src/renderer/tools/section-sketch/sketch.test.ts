import i18next, { type TFunction } from 'i18next';
import { beforeAll, describe, expect, it } from 'vitest';

import type { ProfileState } from '@shared/protocol/generated/sketch';
import type { SketchEntity, SketchParams } from '@shared/protocol/generated/sketch-params';

import { featureView } from '../../features/registry';
import type { FeatureView } from '../../features/types';
import { createFormatter } from '../../i18n/format';
import { buildResources } from '../../i18n/resources';
import { profileSeverity, profileText } from './describe';
import { openEnds, pointOf, xy } from './draftGeometry';
import {
  canRedo,
  canUndo,
  currentDraft,
  pushDraft,
  redoDraft,
  replaceDraft,
  startHistory,
  undoDraft,
} from './draftHistory';
import { closeGap, deleteEntity, formCorner, lineBetween, setLineValue } from './edits';
import {
  endForAngle,
  endForLength,
  intersectCarriers,
  lineAngle,
  lineLength,
  type Vec2,
} from './sketchMath';

const format = createFormatter('de-DE');
let t: TFunction;
// Through the registry: it loads every feature view before the sketch view is used.
const sketchView = featureView('sketch') as FeatureView<'sketch'>;

beforeAll(async () => {
  const instance = i18next.createInstance();
  await instance.init({
    resources: buildResources(),
    lng: 'de',
    interpolation: { escapeValue: false },
  });
  t = instance.t;
});

function expectPoint(actual: Vec2, expected: Vec2): void {
  expect(actual[0]).toBeCloseTo(expected[0], 9);
  expect(actual[1]).toBeCloseTo(expected[1], 9);
}

const line = (id: string, start: string, end: string): SketchEntity => ({
  type: 'line',
  id,
  start,
  end,
  origin: 'fit',
});

/** Two fitted lines of a corner that the fit left open: (0,0)-(40,0) and (50,10)-(50,60). */
function openCorner(): SketchParams {
  return {
    section: {
      type: 'planar',
      plane: { type: 'standard', plane: 'XY' },
      offset: 0,
      sectionOffset: 0,
      xDirection: null,
      flip: false,
    },
    tolerance: null,
    noise: 0.02,
    points: [
      { id: 'p1', x: 0, y: 0, fixed: false },
      { id: 'p2', x: 40, y: 0, fixed: false },
      { id: 'p3', x: 50, y: 10, fixed: false },
      { id: 'p4', x: 50, y: 60, fixed: false },
    ],
    entities: [line('e1', 'p1', 'p2'), line('e2', 'p3', 'p4')],
    constraints: [{ kind: 'perpendicular', refs: ['e1', 'e2'] }],
    snaps: [],
    dimensions: [],
    rejectedSnaps: [],
    shapes: [],
  };
}

describe('line values and end points', () => {
  const start: Vec2 = [10, 5];
  const end: Vec2 = [13, 9];

  it('measures length and direction', () => {
    expect(lineLength(start, end)).toBeCloseTo(5, 12);
    expect(lineAngle(start, end)).toBeCloseTo((Math.atan2(4, 3) * 180) / Math.PI, 12);
    expect(lineAngle([0, 0], [0, -1])).toBeCloseTo(270, 12);
  });

  it('a typed length moves the end along the line', () => {
    const moved = endForLength(start, end, 10);
    expectPoint(moved, [16, 13]);
    expect(lineAngle(start, moved)).toBeCloseTo(lineAngle(start, end), 12);
  });

  it('a typed angle turns the end about the start and keeps the length', () => {
    const moved = endForAngle(start, end, 90);
    expectPoint(moved, [10, 10]);
    expect(lineLength(start, moved)).toBeCloseTo(5, 12);
  });

  it('length and angle round-trip through the end point', () => {
    const moved = endForAngle(start, endForLength(start, end, 42.5), 123);
    expect(lineLength(start, moved)).toBeCloseTo(42.5, 9);
    expect(lineAngle(start, moved)).toBeCloseTo(123, 9);
  });

  it('a typed value on a fitted line becomes a dimension kept by the refit', () => {
    const edited = setLineValue(openCorner(), 'e1', 'length', 50);
    expectPoint(xy(pointOf(edited, 'p2')), [50, 0]);
    expect(edited.dimensions).toEqual([{ entity: 'e1', kind: 'length', value: 50 }]);
  });
});

describe('Ecke bilden', () => {
  it('intersects lines, a line with a circle and two circles nearest to the hint', () => {
    const horizontal = { kind: 'line', point: [0, 0], direction: [1, 0] } as const;
    const vertical = { kind: 'line', point: [50, 10], direction: [0, 1] } as const;
    const circle = { kind: 'circle', center: [0, 0], radius: 5 } as const;
    expectPoint(intersectCarriers(horizontal, vertical, [45, 5]) as Vec2, [50, 0]);
    expectPoint(intersectCarriers(horizontal, circle, [4, 1]) as Vec2, [5, 0]);
    expectPoint(intersectCarriers(circle, horizontal, [-4, 1]) as Vec2, [-5, 0]);
    const other = { kind: 'circle', center: [8, 0], radius: 5 } as const;
    expectPoint(intersectCarriers(circle, other, [4, 5]) as Vec2, [4, 3]);
    const parallel = { kind: 'line', point: [0, 3], direction: [2, 0] } as const;
    expect(intersectCarriers(horizontal, parallel, [0, 0])).toBeNull();
  });

  it('extends both lines to their intersection and joins them in one point', () => {
    const result = formCorner(openCorner(), 'e1', 'e2');
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const [first, second] = result.sketch.entities as Extract<SketchEntity, { type: 'line' }>[];
    expect(first?.end).toBe(second?.start);
    expectPoint(xy(pointOf(result.sketch, first?.end ?? '')), [50, 0]);
    expect(result.sketch.points).toHaveLength(3);
    expect(openEnds(result.sketch).map((point) => point.id)).toEqual(['p1', 'p4']);
  });

  it('refuses parallel lines and circles', () => {
    const sketch = openCorner();
    const parallel: SketchParams = {
      ...sketch,
      points: [
        ...sketch.points,
        { id: 'p5', x: 0, y: 20, fixed: false },
        { id: 'p6', x: 40, y: 20, fixed: false },
      ],
      entities: [...sketch.entities, line('e3', 'p5', 'p6')],
    };
    expect(formCorner(parallel, 'e1', 'e3')).toEqual({ ok: false, reason: 'noIntersection' });
    const withCircle: SketchParams = {
      ...sketch,
      entities: [
        ...sketch.entities,
        { type: 'circle', id: 'e3', center: [20, 30], radius: 6, origin: 'fit' },
      ],
    };
    expect(formCorner(withCircle, 'e1', 'e3')).toEqual({ ok: false, reason: 'notConnectable' });
  });
});

describe('drawing and deleting', () => {
  it('closes the gap between the two nearest open ends with a drawn line', () => {
    const result = closeGap(openCorner());
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const added = result.sketch.entities.at(-1);
    expect(added).toMatchObject({
      type: 'line',
      id: 'e3',
      start: 'p2',
      end: 'p3',
      origin: 'drawn',
    });
  });

  it('does not draw a line of zero length', () => {
    expect(lineBetween(openCorner(), 'p1', 'p1')).toEqual({ ok: false, reason: 'samePoint' });
  });

  it('deleting an entity drops its constraints and unused points', () => {
    const sketch = deleteEntity(openCorner(), 'e2');
    expect(sketch.entities.map((entity) => entity.id)).toEqual(['e1']);
    expect(sketch.constraints).toEqual([]);
    expect(sketch.points.map((point) => point.id)).toEqual(['p1', 'p2']);
  });
});

describe('profile state', () => {
  const profile = (overrides: Partial<ProfileState>): ProfileState => ({
    closed: false,
    loops: [],
    openEntities: [],
    gaps: [],
    branchPoints: [],
    ...overrides,
  });

  it('names closed, open, branched and empty profiles', () => {
    expect(profileText(profile({ closed: true, loops: ['a', 'b'] }), 12, t)).toBe(
      'Profil geschlossen: 2 Konturen',
    );
    expect(profileText(profile({ gaps: [[1, 2]] }), 3, t)).toBe('Profil offen: 1 Lücke');
    expect(profileText(profile({ branchPoints: ['p1'] }), 3, t)).toMatch(/^Profil verzweigt/);
    expect(profileText(null, 0, t)).toBe('Keine Elemente');
  });

  it('warns only when the profile is open or branched', () => {
    expect(profileSeverity(profile({ closed: true, loops: ['a'] }))).toBe('info');
    expect(profileSeverity(profile({ gaps: [[0, 0]] }))).toBe('warning');
    expect(profileSeverity(profile({ closed: true, branchPoints: ['p1'] }))).toBe('warning');
  });

  it('the feature summary counts entities and states the profile', () => {
    expect(sketchView.summary?.(openCorner(), format, t)).toBe('2 Elemente, Profil offen');
    const corner = formCorner(openCorner(), 'e1', 'e2');
    if (!corner.ok) throw new Error('corner expected');
    const closed = closeGap(corner.sketch);
    if (!closed.ok) throw new Error('line expected');
    expect(sketchView.summary?.(closed.sketch, format, t)).toBe('3 Elemente, Profil geschlossen');
  });
});

describe('draft undo', () => {
  it('undoes and redoes edits; a refit replaces its edit without a new step', () => {
    let history = startHistory(openCorner());
    expect(canUndo(history)).toBe(false);
    const deleted = deleteEntity(currentDraft(history), 'e2');
    history = pushDraft(history, deleted);
    history = replaceDraft(history, { ...deleted, noise: 0.03 });
    expect(history.entries).toHaveLength(2);
    history = undoDraft(history);
    expect(currentDraft(history).entities).toHaveLength(2);
    expect(canRedo(history)).toBe(true);
    history = redoDraft(history);
    expect(currentDraft(history).noise).toBe(0.03);
  });

  it('a new edit after undo drops the redo branch', () => {
    let history = pushDraft(startHistory(openCorner()), deleteEntity(openCorner(), 'e1'));
    history = undoDraft(history);
    history = pushDraft(history, deleteEntity(openCorner(), 'e2'));
    expect(canRedo(history)).toBe(false);
    expect(currentDraft(history).entities.map((entity) => entity.id)).toEqual(['e1']);
    expect(undoDraft(undoDraft(undoDraft(history))).position).toBe(0);
  });
});
