import { describe, expect, it } from 'vitest';

import { gridFixture } from './gridFixture';
import { LimitSurface } from './limitSurface';
import { mergePoints, removeQuads, subdivide } from './netBuild';
import { NetHistory } from './netModel';
import { limitsOf, placeLimits } from './netDragSolve';
import { carriedPins, carryPins, fixedMask } from './netPins';
import { NetPoints } from './netPoints';

describe('fixedMask', () => {
  it('holds the pinned points, and with a choice everything not chosen', () => {
    expect(fixedMask(4, new Set(), new Set())).toBeNull();
    expect([...(fixedMask(4, new Set([1]), new Set()) ?? [])]).toEqual([0, 1, 0, 0]);
    expect([...(fixedMask(4, new Set([1]), new Set([1, 2])) ?? [])]).toEqual([1, 1, 0, 1]);
  });
});

describe('carryPins', () => {
  const { net, id } = gridFixture(5);

  it('keeps the numbers when a fit moves points or an edit appends some', () => {
    const finer = subdivide(net).net;
    expect(carryPins(net, finer, [id(2, 2), id(4, 4)])).toEqual([id(2, 2), id(4, 4)]);
    // The kernel holds pinned points with a large weight, not bit for bit.
    const fitted = { ...net, vertices: net.vertices.map((value) => value + 1e-9) };
    expect(carryPins(net, fitted, [id(2, 2)])).toEqual([id(2, 2)]);
  });

  it('follows renumbered points and drops deleted ones', () => {
    // Delete the quads at the corner (0, 0): point 0 goes, later points move down.
    const rest = removeQuads(net, (corners) => corners.includes(id(0, 0)));
    if (!rest) throw new Error('nothing removed');
    expect(carryPins(net, rest, [id(0, 0), id(2, 2)])).toEqual([null, id(2, 2) - 1]);
    // Welding drops the welded point; its pin goes, the others follow.
    const pair = {
      vertices: Float64Array.from({ length: 24 }, (_, i) => i),
      quads: Uint32Array.from([0, 1, 2, 3, 4, 5, 6, 7]),
    };
    const welded = mergePoints(pair, 5, 2);
    if (!welded) throw new Error('not welded');
    expect(carryPins(pair, welded, [5, 6, 1])).toEqual([null, 5, 1]);
  });
});

describe('placeLimits', () => {
  it('brings the pinned limit points back after their neighbours moved', () => {
    const grid = gridFixture(9);
    const surface = new LimitSurface(grid.map, 81);
    surface.evaluate(grid.net.vertices);
    const pinned = [grid.id(4, 4), grid.id(4, 5)];
    const anchors = limitsOf(surface, pinned);
    // A fit moved every other control point up and held the pinned ones (kernel `fixed`).
    const vertices = grid.net.vertices.slice();
    for (let control = 0; control < 81; control += 1)
      if (!pinned.includes(control)) vertices[control * 3 + 2] = 0.5;
    surface.evaluate(vertices);
    expect(surface.limitPoint(pinned[0]!)[2]).toBeGreaterThan(0.1);
    placeLimits(surface, vertices, pinned, anchors);
    for (const [index, control] of pinned.entries())
      for (let axis = 0; axis < 3; axis += 1)
        expect(surface.limitPoint(control)[axis]).toBeCloseTo(anchors[index * 3 + axis]!, 5);
  });

  it('takes the anchors of the carried pins only', () => {
    const grid = gridFixture(5);
    const surface = new LimitSurface(grid.map, 25);
    surface.evaluate(grid.net.vertices);
    const rest = removeQuads(grid.net, (corners) => corners.includes(0));
    if (!rest) throw new Error('nothing removed');
    const { pins, anchors } = carriedPins(surface, grid.net, rest, [0, grid.id(2, 2)]);
    expect(pins).toEqual([grid.id(2, 2) - 1]);
    expect([...(anchors ?? [])]).toEqual([...surface.limitPoint(grid.id(2, 2))]);
  });
});

describe('pins in the editor state', () => {
  it('pins and releases chosen points and counts them', () => {
    const points = new NetPoints();
    points.choose([1, 2], 'replace');
    expect(points.pinChosen(true)).toBe(true);
    expect(points.pinChosen(true)).toBe(false);
    expect(points.counts()).toEqual({ selected: 2, pinned: 2, chosenPinned: 2 });
    points.choose([2], 'replace');
    points.pinChosen(false);
    expect([...points.pinned]).toEqual([1]);
    points.renumbered(1, []);
    expect(points.pinned.size).toBe(0);
  });

  it('survive undo and redo with the net they belong to', () => {
    const history = new NetHistory();
    const net = { vertices: Float64Array.from([0, 0, 0, 1, 0, 0]), quads: new Uint32Array() };
    history.reset(net);
    history.push(net, [1]);
    history.push({ ...net, vertices: Float64Array.from([0, 0, 0, 1, 0, 2]) }, [1]);
    expect(history.undo()?.pinned).toEqual([1]);
    expect(history.undo()?.pinned).toEqual([]);
    expect(history.redo()?.pinned).toEqual([1]);
  });
});
