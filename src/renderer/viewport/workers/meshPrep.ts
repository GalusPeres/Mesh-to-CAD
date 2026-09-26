// Scan preparation that runs off the UI thread (meshPrep.worker.ts): de-indexing,
// normal packing, draw chunks, face centroids and normals, and face adjacency.
// Pure functions, so they are tested directly and also serve as the in-thread
// fallback where a worker cannot start.

/** Faces per draw chunk. Each chunk is uploaded in its own frame (about 10 MB). */
export const CHUNK_FACES = 1 << 17;

/** Expand an indexed (n, 3) float array to one entry per face corner. */
export function deIndex(source: Float32Array, indices: Uint32Array): Float32Array {
  const result = new Float32Array(indices.length * 3);
  for (let corner = 0; corner < indices.length; corner += 1) {
    const vertex = (indices[corner] ?? 0) * 3;
    const target = corner * 3;
    result[target] = source[vertex] ?? 0;
    result[target + 1] = source[vertex + 1] ?? 0;
    result[target + 2] = source[vertex + 2] ?? 0;
  }
  return result;
}

const INT16_MAX = 32767;

/**
 * Vertex normals per face corner as 4 x int16 (normalised, w = 0). Four
 * components keep every vertex 8-byte aligned, a format Direct3D 11 (ANGLE)
 * reads natively; three components would be converted on the CPU.
 */
export function packCornerNormals(normals: Float32Array, indices: Uint32Array): Int16Array {
  const packed = new Int16Array(indices.length * 4);
  for (let corner = 0; corner < indices.length; corner += 1) {
    const vertex = (indices[corner] ?? 0) * 3;
    const x = normals[vertex] ?? 0;
    const y = normals[vertex + 1] ?? 0;
    const z = normals[vertex + 2] ?? 0;
    const scale = INT16_MAX / (Math.hypot(x, y, z) || 1);
    const target = corner * 4;
    packed[target] = Math.round(x * scale);
    packed[target + 1] = Math.round(y * scale);
    packed[target + 2] = Math.round(z * scale);
  }
  return packed;
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
    const f = face * 3;
    centroids[f] = (ax + bx + cx) / 3;
    centroids[f + 1] = (ay + by + cy) / 3;
    centroids[f + 2] = (az + bz + cz) / 3;
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
    normals[f] = nx / length;
    normals[f + 1] = ny / length;
    normals[f + 2] = nz / length;
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
  const low = new Uint32Array(edgeCount);
  const high = new Uint32Array(edgeCount);
  for (let edge = 0; edge < edgeCount; edge += 1) {
    const slot = edge % 3;
    const a = indices[edge] ?? 0;
    const b = indices[edge - slot + ((slot + 1) % 3)] ?? 0;
    low[edge] = a < b ? a : b;
    high[edge] = a < b ? b : a;
  }
  const start = new Uint32Array(vertexCount + 1);
  for (let edge = 0; edge < edgeCount; edge += 1) {
    const vertex = low[edge] ?? 0;
    start[vertex + 1] = (start[vertex + 1] ?? 0) + 1;
  }
  for (let vertex = 0; vertex < vertexCount; vertex += 1)
    start[vertex + 1] = (start[vertex + 1] ?? 0) + (start[vertex] ?? 0);
  const fill = start.slice(0, vertexCount);
  const bucket = new Uint32Array(edgeCount);
  for (let edge = 0; edge < edgeCount; edge += 1) {
    const vertex = low[edge] ?? 0;
    bucket[fill[vertex] ?? 0] = edge;
    fill[vertex] = (fill[vertex] ?? 0) + 1;
  }
  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    const end = start[vertex + 1] ?? 0;
    for (let i = start[vertex] ?? 0; i < end; i += 1) {
      const edge = bucket[i] ?? 0;
      const other = high[edge];
      let match = -1;
      let count = 0;
      for (let j = start[vertex] ?? 0; j < end; j += 1) {
        const candidate = bucket[j] ?? 0;
        if (candidate === edge || high[candidate] !== other) continue;
        match = candidate;
        count += 1;
      }
      // A manifold edge is shared by exactly two faces.
      if (count === 1) neighbours[edge] = Math.floor(match / 3);
    }
  }
  return neighbours;
}

/**
 * Axis-aligned bounds per draw chunk of `chunkFaces` faces, 6 floats each
 * (min xyz, max xyz), followed by the bounds of the whole scan.
 */
export function chunkBounds(positions: Float32Array, chunkFaces = CHUNK_FACES): Float32Array {
  const faceCount = positions.length / 9;
  const chunkCount = Math.ceil(faceCount / chunkFaces);
  const bounds = new Float32Array((chunkCount + 1) * 6);
  const total = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (let chunk = 0; chunk < chunkCount; chunk += 1) {
    const box = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
    const end = Math.min(faceCount, (chunk + 1) * chunkFaces) * 9;
    for (let i = chunk * chunkFaces * 9; i < end; i += 3) {
      for (let axis = 0; axis < 3; axis += 1) {
        const value = positions[i + axis] ?? 0;
        if (value < (box[axis] ?? 0)) box[axis] = value;
        if (value > (box[axis + 3] ?? 0)) box[axis + 3] = value;
      }
    }
    bounds.set(box, chunk * 6);
    for (let axis = 0; axis < 3; axis += 1) {
      total[axis] = Math.min(total[axis] ?? 0, box[axis] ?? 0);
      total[axis + 3] = Math.max(total[axis + 3] ?? 0, box[axis + 3] ?? 0);
    }
  }
  bounds.set(chunkCount > 0 ? total : [0, 0, 0, 0, 0, 0], chunkCount * 6);
  return bounds;
}

export interface MeshPrepInput {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
}

/** What the viewport needs to draw the scan (first worker message). */
export interface PreparedGeometry {
  /** 9 floats per face, scan-local. */
  positions: Float32Array;
  /** 12 int16 per face (4 per corner). */
  normals: Int16Array;
  /** `chunkBounds` output. */
  bounds: Float32Array;
}

/** What picking, selection growth and the section outline need (second message). */
export interface PreparedTopology {
  centroids: Float32Array;
  faceNormals: Float32Array;
  neighbours: Int32Array;
}

export function prepareGeometry(input: MeshPrepInput): PreparedGeometry {
  const positions = deIndex(input.positions, input.indices);
  return {
    positions,
    normals: packCornerNormals(input.normals, input.indices),
    bounds: chunkBounds(positions),
  };
}

export function prepareTopology(
  geometry: PreparedGeometry,
  indices: Uint32Array,
  vertexCount: number,
): PreparedTopology {
  const { centroids, normals } = faceCentroidsAndNormals(geometry.positions);
  return { centroids, faceNormals: normals, neighbours: faceAdjacency(indices, vertexCount) };
}
