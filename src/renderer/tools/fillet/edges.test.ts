import { describe, expect, it } from 'vitest';

import {
  type EdgePayload,
  edgeFaceTags,
  edgeForRef,
  edgeRef,
  edgeSegments,
  nearestEdge,
  pickTolerance,
  touchesFeature,
} from './edges';

/**
 * Top edges of a 30 x 20 x 10 block after a slot cut the top cap in two:
 * edge 0 and 1 lie on y = 0 (left and right of the slot), both between the top
 * cap (face 3) and the front side (face 0); edge 2 runs along x = 30 (face 3 / face 1).
 */
const payload: EdgePayload = {
  segments: new Float32Array(
    [
      [0, 0, 10, 12, 0, 10], // edge 0
      [18, 0, 10, 30, 0, 10], // edge 1
      [30, 0, 10, 30, 10, 10], // edge 2, two segments
      [30, 10, 10, 30, 20, 10],
    ].flat(),
  ),
  ids: new Uint32Array([0, 1, 2, 2]),
  faces: new Uint32Array([0, 3, 3, 0, 1, 3, 1, 3]),
};
const faceTags = ['f2:side:e0', 'f2:side:e1', 'f2:cap:start', 'f2:cap:end'];

describe('building an edge reference from a pick', () => {
  it('maps the payload faces through the body face tags', () => {
    expect(edgeFaceTags(payload, faceTags, 2)).toEqual(['f2:side:e1', 'f2:cap:end']);
    expect(edgeRef(payload, faceTags, 1, [25, 0, 10])).toEqual({
      faces: ['f2:cap:end', 'f2:side:e0'],
      point: [25, 0, 10],
    });
  });

  it('gives nothing without face pairs or for unknown edges', () => {
    expect(edgeFaceTags({ ...payload, faces: null }, faceTags, 0)).toBeNull();
    expect(edgeRef(payload, faceTags, 9, [0, 0, 0])).toBeNull();
  });

  it('finds the nearest edge within the tolerance', () => {
    expect(nearestEdge(payload, [25, 0.01, 10], 0.1)?.edge).toBe(1);
    expect(nearestEdge(payload, [30, 15, 10.02], 0.1)?.edge).toBe(2);
    expect(nearestEdge(payload, [15, 10, 10], 0.1)).toBeNull();
  });
});

describe('resolving a stored reference', () => {
  it('uses the point to choose between edges with the same face tags', () => {
    const faces: [string, string] = ['f2:cap:end', 'f2:side:e0'];
    expect(edgeForRef(payload, faceTags, { faces, point: [2, 0, 10] })).toBe(0);
    expect(edgeForRef(payload, faceTags, { faces, point: [28, 0, 10] })).toBe(1);
  });

  it('takes the only candidate even when the point moved', () => {
    const ref = {
      faces: ['f2:side:e1', 'f2:cap:end'] as [string, string],
      point: [30, 5, 15] as [number, number, number],
    };
    expect(edgeForRef(payload, faceTags, ref)).toBe(2);
  });

  it('reports edges that no longer exist', () => {
    const ref = {
      faces: ['f2:cap:start', 'f9:x'] as [string, string],
      point: [0, 0, 0] as [number, number, number],
    };
    expect(edgeForRef(payload, faceTags, ref)).toBeNull();
  });
});

describe('edge geometry', () => {
  it('collects the segments of the given edges', () => {
    expect(edgeSegments(payload, new Set([2]))).toHaveLength(12);
  });

  it('scales the pick tolerance with the body', () => {
    expect(pickTolerance(payload)).toBeCloseTo(Math.hypot(30, 20) * 0.002, 6);
  });

  it('recognises faces made by the edited feature', () => {
    const ref = {
      faces: ['f5:fillet:0', 'f2:cap:end'] as [string, string],
      point: [0, 0, 0] as [number, number, number],
    };
    expect(touchesFeature(ref, 'f5')).toBe(true);
    expect(touchesFeature(ref, 'f2')).toBe(true);
    expect(touchesFeature(ref, 'f7')).toBe(false);
    expect(touchesFeature(ref, null)).toBe(false);
  });
});
