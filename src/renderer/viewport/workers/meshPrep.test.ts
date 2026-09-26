import { describe, expect, it } from 'vitest';

import {
  chunkBounds,
  deIndex,
  faceAdjacency,
  faceCentroidsAndNormals,
  packCornerNormals,
} from './meshPrep';
import { prepareScan } from './scanWorkers';

// A closed tetrahedron with outward winding.
const TETRA_POSITIONS = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]);
const TETRA_INDICES = new Uint32Array([0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3]);

describe('scan preparation', () => {
  it('de-indexes so that face i owns corners 3i..3i+2', () => {
    const positions = deIndex(TETRA_POSITIONS, TETRA_INDICES);
    expect(positions).toHaveLength(4 * 9);
    // Face 1 = vertices 0, 1, 3.
    expect(Array.from(positions.subarray(9, 18))).toEqual([0, 0, 0, 1, 0, 0, 0, 0, 1]);
  });

  it('packs corner normals as four normalised int16 with w = 0', () => {
    const normals = new Float32Array([0, 0, 2, 3, 4, 0]);
    const packed = packCornerNormals(normals, new Uint32Array([1, 0, 1]));
    expect(Array.from(packed.subarray(0, 4))).toEqual([19660, 26214, 0, 0]);
    expect(Array.from(packed.subarray(4, 8))).toEqual([0, 0, 32767, 0]);
    // Decoded length stays within 1e-4 of unit length.
    const [x = 0, y = 0, z = 0] = Array.from(packed.subarray(8, 11), (value) => value / 32767);
    expect(Math.abs(Math.hypot(x, y, z) - 1)).toBeLessThan(1e-4);
  });

  it('computes face centroids and outward unit normals', () => {
    const { centroids, normals } = faceCentroidsAndNormals(deIndex(TETRA_POSITIONS, TETRA_INDICES));
    expect(Array.from(centroids.subarray(0, 3)).map((v) => +v.toFixed(6))).toEqual([
      0.333333, 0.333333, 0,
    ]);
    expect(Array.from(normals.subarray(0, 3))).toEqual([0, 0, -1]);
    const slanted = Array.from(normals.subarray(9, 12));
    for (const component of slanted) expect(component).toBeCloseTo(1 / Math.sqrt(3), 6);
  });

  it('finds the neighbour across every edge of a closed mesh', () => {
    const neighbours = faceAdjacency(TETRA_INDICES, 4);
    for (let face = 0; face < 4; face += 1) {
      const around = Array.from(neighbours.subarray(face * 3, face * 3 + 3)).sort();
      expect(around).toEqual([0, 1, 2, 3].filter((other) => other !== face));
    }
    // Edge slot 0 of face 0 runs from vertex 0 to vertex 2, shared with face 2.
    expect(neighbours[0]).toBe(2);
  });

  it('marks open and non-manifold edges with -1', () => {
    // Three triangles share the edge 0-1 (non-manifold); the others are open.
    const indices = new Uint32Array([0, 1, 2, 1, 0, 3, 0, 1, 4]);
    const neighbours = faceAdjacency(indices, 5);
    expect(Array.from(neighbours)).toEqual(new Array(9).fill(-1));
    const strip = faceAdjacency(new Uint32Array([0, 1, 2, 2, 1, 3]), 4);
    expect(Array.from(strip)).toEqual([-1, 1, -1, 0, -1, -1]);
  });

  it('computes bounds per draw chunk and for the whole scan', () => {
    const positions = deIndex(TETRA_POSITIONS, TETRA_INDICES);
    const bounds = chunkBounds(positions, 3);
    expect(bounds).toHaveLength(3 * 6);
    expect(Array.from(bounds.subarray(0, 6))).toEqual([0, 0, 0, 1, 1, 1]);
    // The second chunk holds face 3 only: vertices 1, 2, 3.
    expect(Array.from(bounds.subarray(6, 12))).toEqual([0, 0, 0, 1, 1, 1]);
    expect(Array.from(bounds.subarray(12, 18))).toEqual([0, 0, 0, 1, 1, 1]);
    const single = chunkBounds(deIndex(TETRA_POSITIONS, new Uint32Array([1, 2, 3])), 3);
    expect(Array.from(single.subarray(0, 6))).toEqual([0, 0, 0, 1, 1, 1]);
  });

  it('delivers geometry, topology and a BVH in face order on the UI thread', async () => {
    const normals = new Float32Array(TETRA_POSITIONS.length).fill(0.5);
    const preparation = prepareScan(
      { positions: TETRA_POSITIONS, normals, indices: TETRA_INDICES },
      { inThread: true },
    );
    const geometry = await preparation.geometry;
    const topology = await preparation.topology;
    expect(geometry.positions).toHaveLength(36);
    expect(geometry.normals).toHaveLength(48);
    expect(topology.neighbours).toHaveLength(12);
    expect(topology.bvh.indirectBuffer).not.toBeNull();
    expect(Array.from(topology.indices)).toEqual(Array.from(TETRA_INDICES));
  });
});
