// Scan preparation that runs off the UI thread (meshPrep.worker.ts): de-indexing,
// face centroids and normals, and face adjacency. Pure functions, so they are
// tested directly and used as an in-thread fallback where workers are missing.

/** Expand indexed arrays to one vertex per face corner. */
export function deIndex(source: Float32Array, indices: Uint32Array): Float32Array {
  const result = new Float32Array(indices.length * 3);
  for (let corner = 0; corner < indices.length; corner += 1) {
    const vertex = (indices[corner] ?? 0) * 3;
    result[corner * 3] = source[vertex] ?? 0;
    result[corner * 3 + 1] = source[vertex + 1] ?? 0;
    result[corner * 3 + 2] = source[vertex + 2] ?? 0;
  }
  return result;
}

/** Face centroids and unit face normals of a de-indexed triangle list. */
export function faceCentroidsAndNormals(positions: Float32Array): {
  centroids: Float32Array;
  normals: Float32Array;
} {
  const faceCount = positions.length / 9;
  const centroids = new Float32Array(faceCount * 3);
  const normals = new Float32Array(faceCount * 3);
  for (let face = 0; face < faceCount; face += 1) {
    const o = face * 9;
    const ax = positions[o] ?? 0;
    const ay = positions[o + 1] ?? 0;
    const az = positions[o + 2] ?? 0;
    const bx = positions[o + 3] ?? 0;
    const by = positions[o + 4] ?? 0;
    const bz = positions[o + 5] ?? 0;
    const cx = positions[o + 6] ?? 0;
    const cy = positions[o + 7] ?? 0;
    const cz = positions[o + 8] ?? 0;
    centroids[face * 3] = (ax + bx + cx) / 3;
    centroids[face * 3 + 1] = (ay + by + cy) / 3;
    centroids[face * 3 + 2] = (az + bz + cz) / 3;
    const ux = bx - ax;
    const uy = by - ay;
    const uz = bz - az;
    const vx = cx - ax;
    const vy = cy - ay;
    const vz = cz - az;
    const nx = uy * vz - uz * vy;
    const ny = uz * vx - ux * vz;
    const nz = ux * vy - uy * vx;
    const length = Math.hypot(nx, ny, nz) || 1;
    normals[face * 3] = nx / length;
    normals[face * 3 + 1] = ny / length;
    normals[face * 3 + 2] = nz / length;
  }
  return { centroids, normals };
}

/**
 * Neighbour face across each edge (slot k = edge from corner k to corner k+1),
 * -1 at open or non-manifold edges. Linear time: edges are bucketed by their
 * smaller vertex id (CSR), so no string keys or hash maps are needed.
 */
export function faceAdjacency(indices: Uint32Array, vertexCount: number): Int32Array {
  const edgeCount = indices.length;
  const neighbours = new Int32Array(edgeCount).fill(-1);
  const start = new Uint32Array(vertexCount + 1);
  const low = (edge: number) => {
    const face = edge - (edge % 3);
    const a = indices[edge] ?? 0;
    const b = indices[face + (((edge % 3) + 1) % 3)] ?? 0;
    return a < b ? a : b;
  };
  const high = (edge: number) => {
    const face = edge - (edge % 3);
    const a = indices[edge] ?? 0;
    const b = indices[face + (((edge % 3) + 1) % 3)] ?? 0;
    return a < b ? b : a;
  };
  for (let edge = 0; edge < edgeCount; edge += 1)
    start[low(edge) + 1] = (start[low(edge) + 1] ?? 0) + 1;
  for (let vertex = 0; vertex < vertexCount; vertex += 1)
    start[vertex + 1] = (start[vertex + 1] ?? 0) + (start[vertex] ?? 0);
  const fill = start.slice(0, vertexCount);
  const bucket = new Uint32Array(edgeCount);
  for (let edge = 0; edge < edgeCount; edge += 1) {
    const vertex = low(edge);
    bucket[fill[vertex] ?? 0] = edge;
    fill[vertex] = (fill[vertex] ?? 0) + 1;
  }
  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    const end = start[vertex + 1] ?? 0;
    for (let i = start[vertex] ?? 0; i < end; i += 1) {
      const edge = bucket[i] ?? 0;
      const other = high(edge);
      let match = -1;
      let count = 0;
      for (let j = start[vertex] ?? 0; j < end; j += 1) {
        const candidate = bucket[j] ?? 0;
        if (candidate === edge || high(candidate) !== other) continue;
        match = candidate;
        count += 1;
      }
      // Exactly two faces share a manifold edge.
      if (count === 1) neighbours[edge] = Math.floor(match / 3);
    }
  }
  return neighbours;
}

export interface MeshPrepInput {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
}

export interface MeshPrepResult {
  positions: Float32Array;
  normals: Float32Array;
  centroids: Float32Array;
  faceNormals: Float32Array;
  neighbours: Int32Array;
}

export function prepareMesh(input: MeshPrepInput): MeshPrepResult {
  const positions = deIndex(input.positions, input.indices);
  const normals = deIndex(input.normals, input.indices);
  const { centroids, normals: faceNormals } = faceCentroidsAndNormals(positions);
  const neighbours = faceAdjacency(input.indices, input.positions.length / 3);
  return { positions, normals, centroids, faceNormals, neighbours };
}
