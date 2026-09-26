// Worker: prepares a scan for display (docs/ARCHITECTURE.md 5.8) so the UI thread
// only uploads buffers. Two messages: the drawable geometry as soon as it is
// de-indexed, then centroids, adjacency and the BVH. A copy of the centroids and
// face normals goes straight to the polygon-picking worker through `pickPort`.

import { BufferAttribute, BufferGeometry } from 'three';
import { MeshBVH } from 'three-mesh-bvh';

import {
  type MeshPrepInput,
  type PreparedGeometry,
  prepareGeometry,
  prepareTopology,
} from './meshPrep';
import type { MeshPrepReply, PolygonPickScan } from './messages';

interface PrepRequest extends MeshPrepInput {
  pickPort: MessagePort | null;
}

const post = (message: MeshPrepReply, transfer: Transferable[]) =>
  (self as unknown as Worker).postMessage(message, transfer);

function run({ positions, normals, indices, pickPort }: PrepRequest): void {
  const geometry: PreparedGeometry = prepareGeometry({ positions, normals, indices });
  // The UI thread receives its own copy; the worker keeps building on the original.
  const drawn = geometry.positions.slice();
  post({ type: 'geometry', positions: drawn, normals: geometry.normals, bounds: geometry.bounds }, [
    drawn.buffer,
    geometry.normals.buffer,
    geometry.bounds.buffer,
  ]);

  const topology = prepareTopology(geometry, indices, positions.length / 3);
  if (pickPort) {
    const scan: PolygonPickScan = {
      centroids: topology.centroids.slice(),
      faceNormals: topology.faceNormals.slice(),
    };
    pickPort.postMessage(scan, [scan.centroids.buffer, scan.faceNormals.buffer]);
    pickPort.close();
  }

  const bvhGeometry = new BufferGeometry();
  bvhGeometry.setAttribute('position', new BufferAttribute(geometry.positions, 3));
  const bvh = MeshBVH.serialize(new MeshBVH(bvhGeometry, { indirect: true }), {
    cloneBuffers: false,
  });
  const transfer: Transferable[] = [
    topology.centroids.buffer,
    topology.faceNormals.buffer,
    topology.neighbours.buffer,
    indices.buffer,
    ...bvh.roots,
  ];
  if (bvh.indirectBuffer) transfer.push(bvh.indirectBuffer.buffer);
  post({ type: 'topology', ...topology, bvh, indices }, transfer);
}

self.onmessage = (event: MessageEvent<PrepRequest>) => {
  try {
    run(event.data);
  } catch (error) {
    post({ type: 'error', message: error instanceof Error ? error.message : String(error) }, []);
  }
};
