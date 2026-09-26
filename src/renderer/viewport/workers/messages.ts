// Messages between the viewport and its workers.

import type { SerializedBVH } from 'three-mesh-bvh';

import type { PreparedTopology } from './meshPrep';
import type { PolygonPickQuery } from './polygonPick';

export type MeshPrepReply =
  | { type: 'geometry'; positions: Float32Array; normals: Int16Array; bounds: Float32Array }
  | ({ type: 'topology'; bvh: SerializedBVH; indices: Uint32Array } & PreparedTopology)
  | { type: 'error'; message: string };

/** Sent once per scan from the preparation worker to the polygon-picking worker. */
export interface PolygonPickScan {
  centroids: Float32Array;
  faceNormals: Float32Array;
}

export interface PolygonPickRequest {
  id: number;
  query: PolygonPickQuery;
}

export interface PolygonPickReply {
  id: number;
  faces: Uint32Array | null;
  error?: string;
}
