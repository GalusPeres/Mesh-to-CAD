import { describe, expect, it } from 'vitest';

import type { LimitMapResult } from '@shared/protocol/generated/net';

import { colorize, deviationSummary, heatmapScale } from './heatmap';
import { LimitSurface } from './limitSurface';
import { NetHistory, controlOffsets, irregularCount } from './netModel';

/**
 * Three control points; dense vertices 0-2 are their limits (a symmetric positive
 * definite averaging like Catmull-Clark's), vertex 3 the mean of all three.
 */
function smallMap(): LimitMapResult {
  const rows = [
    [0.6, 0.2, 0.2],
    [0.2, 0.6, 0.2],
    [0.2, 0.2, 0.6],
    [1 / 3, 1 / 3, 1 / 3],
  ];
  const indptr = [0];
  const columns: number[] = [];
  const weights: number[] = [];
  for (const row of rows) {
    row.forEach((weight, column) => {
      columns.push(column);
      weights.push(weight);
    });
    indptr.push(columns.length);
  }
  return {
    rows: Uint32Array.from(indptr),
    columns: Uint32Array.from(columns),
    weights: Float32Array.from(weights),
    triangles: Uint32Array.from([0, 1, 2]),
    segments: Uint32Array.from([0, 1, 1, 2, 2, 0]),
    segmentEdges: Uint32Array.from([0, 1, 2]),
    edges: Uint32Array.from([0, 1, 1, 2, 2, 0]),
    boundaryEdges: Uint8Array.from([1, 1, 1]),
    border: Uint8Array.from([1, 1, 1, 0]),
    faceEdges: Uint8Array.from([1, 1, 1]),
    faceCount: 1,
    level: 1,
    fineCount: 4,
  };
}

const control = Float64Array.from([0, 0, 0, 3, 0, 0, 0, 3, 0]);

describe('LimitSurface', () => {
  it('evaluates every dense vertex as its weighted control points', () => {
    const surface = new LimitSurface(smallMap(), 3);
    surface.evaluate(control);
    expect(surface.limitPoint(1)[0]).toBeCloseTo(0.6 * 3, 5);
    expect(surface.positions[9]).toBeCloseTo(1, 5);
    expect(surface.positions[10]).toBeCloseTo(1, 5);
    expect(surface.ownWeight(2)).toBeCloseTo(0.6, 5);
  });

  it('finds the dense vertices that read a control point, each once', () => {
    const surface = new LimitSurface(smallMap(), 3);
    expect([...surface.rowsOf([0])].sort()).toEqual([0, 1, 2, 3]);
    expect([...surface.rowsOf([0, 1, 2])].sort()).toEqual([0, 1, 2, 3]);
  });
});

describe('controlOffsets', () => {
  it('moves the limit points of the dragged control points by the wanted offset', () => {
    const surface = new LimitSurface(smallMap(), 3);
    const moved = Uint32Array.from([0, 1]);
    const wanted = Float64Array.from([1, 0, 0, 1, 0, 0]);
    const offsets = controlOffsets(surface, moved, wanted);
    const next = control.slice();
    moved.forEach((c, i) => {
      for (let axis = 0; axis < 3; axis += 1) next[c * 3 + axis]! += offsets[i * 3 + axis]!;
    });
    surface.evaluate(control);
    const before = [surface.limitPoint(0), surface.limitPoint(1)];
    surface.evaluate(next);
    expect(surface.limitPoint(0)[0] - before[0]![0]).toBeCloseTo(1, 4);
    expect(surface.limitPoint(1)[0] - before[1]![0]).toBeCloseTo(1, 4);
    expect(surface.limitPoint(0)[1] - before[0]![1]).toBeCloseTo(0, 6);
  });
});

describe('NetHistory', () => {
  it('undoes and redoes copies of the net and drops redo steps on a new change', () => {
    const history = new NetHistory(3);
    const net = (x: number) => ({
      vertices: Float64Array.from([x, 0, 0]),
      quads: new Uint32Array(),
    });
    history.reset(net(0));
    history.push(net(1));
    history.push(net(2));
    expect(history.undo()?.vertices[0]).toBe(1);
    expect(history.undo()?.vertices[0]).toBe(0);
    expect(history.canUndo).toBe(false);
    expect(history.redo()?.vertices[0]).toBe(1);
    history.push(net(5));
    expect(history.canRedo).toBe(false);
    // The limit keeps only the newest three states.
    history.push(net(6));
    expect(history.undo()?.vertices[0]).toBe(5);
    expect(history.undo()?.vertices[0]).toBe(1);
    expect(history.canUndo).toBe(false);
  });
});

describe('irregularCount', () => {
  it('counts inner control points whose valence is not four', () => {
    // A 3 x 3 grid of quads: one inner point of valence 4, the rest on the border.
    const edges: number[] = [];
    const id = (i: number, j: number) => i * 4 + j;
    for (let i = 0; i < 4; i += 1)
      for (let j = 0; j < 4; j += 1) {
        if (i < 3) edges.push(id(i, j), id(i + 1, j));
        if (j < 3) edges.push(id(i, j), id(i, j + 1));
      }
    const boundary = Uint8Array.from({ length: edges.length / 2 }, (_, e) => {
      const a = edges[e * 2]!;
      const b = edges[e * 2 + 1]!;
      const onBorder = (v: number) => v % 4 === 0 || v % 4 === 3 || v < 4 || v >= 12;
      return onBorder(a) && onBorder(b) ? 1 : 0;
    });
    expect(irregularCount(Uint32Array.from(edges), boundary, 16)).toBe(0);
  });
});

describe('heatmap', () => {
  it('colours distances by band and summarises the measured ones', () => {
    const scale = heatmapScale(0.1);
    const distances = Float32Array.from([0, 0.05, 0.3, -0.3, Number.NaN]);
    const colors = new Float32Array(distances.length * 3);
    colorize(distances, scale, colors);
    // Within the tolerance both points get the same (green) colour.
    expect(colors.slice(0, 3)).toEqual(colors.slice(3, 6));
    expect(colors.slice(6, 9)).not.toEqual(colors.slice(9, 12));
    const summary = deviationSummary(distances, 0.1);
    expect(summary.measured).toBe(4);
    expect(summary.withinTolerance).toBeCloseTo(0.5, 6);
    expect(summary.max).toBeCloseTo(0.3, 6);
  });
});
