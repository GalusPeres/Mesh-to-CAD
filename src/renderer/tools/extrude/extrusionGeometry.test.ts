import { describe, expect, it } from 'vitest';

import { type MeshData, findCaps, scanExtent } from './extrusionGeometry';

/** A 40 x 20 x h box as a previewed body: faces 0 (bottom, start cap) and 1 (top, end cap). */
function boxPreview(height: number): MeshData {
  const bottom = [
    [0, 0, 0],
    [40, 0, 0],
    [40, 20, 0],
    [0, 20, 0],
  ];
  const top = bottom.map(([x, y]) => [x!, y!, height]);
  const positions = new Float32Array([...bottom, ...top].flat());
  const indices = new Uint32Array([0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7]);
  return { positions, indices, faceIds: new Uint32Array([0, 0, 1, 1]) };
}

const TAGS = ['f5:cap:start', 'f5:cap:end'];

/** Deterministic pseudo-random numbers (no global random state in tests either). */
function random(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

/** Scan face centroids of a noisy 40 x 20 x 12 block plus a neighbouring 30 mm tower. */
function blockScan(): Float32Array {
  const next = random(7);
  const gauss = () => Math.sqrt(-2 * Math.log(next() + 1e-12)) * Math.cos(2 * Math.PI * next());
  const points: number[] = [];
  for (let i = 0; i < 20000; i++) {
    const x = next() * 40;
    const y = next() * 20;
    points.push(x, y, 12 + 0.03 * gauss()); // top
    points.push(x, y, 0.03 * gauss()); // bottom
  }
  for (let i = 0; i < 40; i++) points.push(next() * 40, next() * 20, 12.25); // spikes
  for (let i = 0; i < 5000; i++) points.push(50 + next() * 10, next() * 10, 30); // outside
  return new Float32Array(points);
}

describe('findCaps', () => {
  it('finds start and end caps by face tag', () => {
    const caps = findCaps(boxPreview(10), TAGS, 'f5');
    expect(caps).not.toBeNull();
    const close = (actual: number[], expected: number[]) =>
      actual.forEach((value, axis) => expect(value).toBeCloseTo(expected[axis]!, 9));
    close(caps!.start, [20, 10, 0]);
    close(caps!.end, [20, 10, 10]);
    close(caps!.direction, [0, 0, 1]);
    expect(caps!.footprint).toHaveLength(18);
  });

  it('gives nothing when a cap is missing', () => {
    expect(findCaps(boxPreview(10), ['f5:cap:start', 'f2:side:e1'], 'f5')).toBeNull();
    expect(findCaps(boxPreview(10), TAGS, 'f6')).toBeNull();
  });
});

describe('scanExtent', () => {
  it('measures the scan above the footprint and ignores spikes and other parts', () => {
    const caps = findCaps(boxPreview(10), TAGS, 'f5')!;
    const extent = scanExtent(blockScan(), caps.footprint, [0, 0, 0], caps.direction);
    expect(extent).not.toBeNull();
    expect(Math.abs(extent! - 12)).toBeLessThan(0.01);
  });

  it('is null when no scan lies in front of the profile', () => {
    const caps = findCaps(boxPreview(10), TAGS, 'f5')!;
    const below = new Float32Array([10, 10, -5, 20, 5, -3]);
    expect(scanExtent(below, caps.footprint, [0, 0, 0], caps.direction)).toBeNull();
  });
});
