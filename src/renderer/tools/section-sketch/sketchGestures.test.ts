import { describe, expect, it } from 'vitest';

import type { EntityFitInfo, SketchFrame } from '@shared/protocol/generated/sketch';
import type { SketchEntity, SketchParams } from '@shared/protocol/generated/sketch-params';

import { deviationLabels } from './deviationLabels';
import {
  type GestureContext,
  gestureAt,
  interiorPoint,
  loopAt,
  strokeGesture,
} from './sketchGestures';
import { selectedEntities, sketchGroups } from './sketchGroups';
import type { Vec2 } from './sketchMath';
import { shapeSizes } from './shapeSizes';

/** Sketch coordinates are screen pixels: 10 px per mm, y up. */
const frame: SketchFrame = {
  origin: [0, 0, 0],
  xDir: [1, 0, 0],
  yDir: [0, 1, 0],
  normal: [0, 0, 1],
  baseOrigin: [0, 0, 0],
  offsetDirection: [0, 0, 1],
  rotational: false,
};
const project = (p: readonly [number, number, number]) => ({ x: 10 * p[0], y: -10 * p[1] });
const screen = (p: Vec2): Vec2 => [10 * p[0], -10 * p[1]];

const square = (cx: number, cy: number, half: number): Vec2[] => [
  [cx - half, cy - half],
  [cx + half, cy - half],
  [cx + half, cy + half],
  [cx - half, cy + half],
];

const line = (id: string, start: string, end: string): SketchEntity => ({
  type: 'line',
  id,
  start,
  end,
  origin: 'fit',
});

/** A slot 8 x 4 around the origin (shape s1), a free corner of two lines and a circle. */
function sketch(): SketchParams {
  const p = (id: string, x: number, y: number) => ({ id, x, y, fixed: false });
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
    noise: null,
    points: [
      p('p1', -2, -2),
      p('p2', 2, -2),
      p('p3', 2, 2),
      p('p4', -2, 2),
      p('p5', 20, 0),
      p('p6', 30, 0),
      p('p7', 30, 10),
    ],
    entities: [
      line('e1', 'p1', 'p2'),
      {
        type: 'arc',
        id: 'e2',
        start: 'p2',
        end: 'p3',
        center: [2, 0],
        radius: 2,
        ccw: true,
        origin: 'fit',
      },
      line('e3', 'p3', 'p4'),
      {
        type: 'arc',
        id: 'e4',
        start: 'p4',
        end: 'p1',
        center: [-2, 0],
        radius: 2,
        ccw: true,
        origin: 'fit',
      },
      line('e5', 'p5', 'p6'),
      line('e6', 'p6', 'p7'),
      { type: 'circle', id: 'e7', center: [0, 20], radius: 3, origin: 'fit' },
    ],
    constraints: [],
    snaps: [],
    dimensions: [],
    rejectedSnaps: [],
    shapes: [{ id: 's1', kind: 'slot', entities: ['e1', 'e2', 'e3', 'e4'] }],
  };
}

const context = (loops: Vec2[][] = []): GestureContext => ({
  sketch: sketch(),
  loops,
  frame,
  project,
});

describe('outlines under the pointer', () => {
  it('picks the smallest outline around a point', () => {
    const loops = [square(0, 0, 10), square(5, 5, 2)];
    expect(loopAt(loops, [5, 5])).toBe(1);
    expect(loopAt(loops, [-5, -5])).toBe(0);
    expect(loopAt(loops, [50, 0])).toBeNull();
  });

  it('finds a point inside a concave outline', () => {
    // A U shape: its centroid lies in the notch, outside the outline.
    const u: Vec2[] = [
      [0, 0],
      [9, 0],
      [9, 9],
      [6, 9],
      [6, 3],
      [3, 3],
      [3, 9],
      [0, 9],
    ];
    const inside = interiorPoint(u);
    expect(inside).not.toBeNull();
    expect(loopAt([u], inside as Vec2)).toBe(0);
  });
});

describe('what a click does', () => {
  it('selects an entity near the cursor, else fits the outline it lies in', () => {
    const loops = [square(0, 20, 4)];
    expect(gestureAt(context(loops), screen([0, -2]), [0, -2], false)).toEqual({
      kind: 'select',
      entity: 'e1',
    });
    expect(gestureAt(context(loops), screen([1, 21]), [1, 21], false)).toEqual({
      kind: 'outline',
      loop: 0,
      at: [1, 21],
    });
    expect(gestureAt(context(loops), screen([60, 60]), [60, 60], false).kind).toBe('none');
  });

  it('rounds a joint with Ctrl and forms a corner across two entities', () => {
    expect(gestureAt(context(), screen([30, 0]), [30, 0], true)).toEqual({
      kind: 'fillet',
      point: 'p6',
    });
    const across: Vec2[] = [screen([25, 0.1]), screen([28, 5]), screen([30, 6])];
    expect(strokeGesture(context(), across)).toEqual({ kind: 'corner', first: 'e5', second: 'e6' });
    expect(strokeGesture(context(), [screen([25, 0]), screen([30, 0.2])])).toEqual({
      kind: 'fillet',
      point: 'p6',
    });
  });
});

describe('groups, sizes and deviation labels', () => {
  it('groups shapes, free profiles and single entities', () => {
    const groups = sketchGroups(sketch());
    expect(groups.map((g) => [g.id, g.kind, g.entities.length])).toEqual([
      ['s1', 'shape', 4],
      ['k5', 'profile', 2],
      ['e7', 'entity', 1],
    ]);
    expect(selectedEntities(groups, 's1')).toEqual(['e1', 'e2', 'e3', 'e4']);
    expect(selectedEntities(groups, 'e2')).toEqual(['e2']);
  });

  it('reads slot sizes from the entities', () => {
    const draft = sketch();
    expect(shapeSizes(draft, draft.shapes[0] as SketchParams['shapes'][number])).toEqual({
      length: 8,
      width: 4,
    });
  });

  it('labels a shape once with its worst entity, per entity when expanded', () => {
    const fit = (entity: string, maxDistance: number): EntityFitInfo => ({
      entity,
      points: 10,
      maxDistance,
      rms: maxDistance / 2,
      share: 1,
      passed: maxDistance < 0.1,
    });
    const fits = ['e1', 'e2', 'e3', 'e4', 'e5', 'e6', 'e7'].map((id, k) => fit(id, 0.01 * (k + 1)));
    const collapsed = deviationLabels(sketch(), fits, []);
    expect(collapsed.map((l) => l.value)).toEqual([0.04, 0.06, 0.07]);
    expect(deviationLabels(sketch(), fits, ['s1'])).toHaveLength(6);
  });
});
