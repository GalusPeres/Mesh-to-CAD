// Worker: prepares a scan for display (docs/ARCHITECTURE.md 5.8) so the UI thread
// only uploads buffers. Builds the BVH too and sends it back serialised.

import { BufferAttribute, BufferGeometry } from 'three';
import { MeshBVH, type SerializedBVH } from 'three-mesh-bvh';

import { type MeshPrepInput, type MeshPrepResult, prepareMesh } from './meshPrep';

export interface MeshPrepMessage extends MeshPrepResult {
  bvh: SerializedBVH;
}

self.onmessage = (event: MessageEvent<MeshPrepInput>) => {
  const result = prepareMesh(event.data);
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(result.positions, 3));
  const bvh = MeshBVH.serialize(new MeshBVH(geometry, { indirect: true }), {
    cloneBuffers: false,
  });
  const message: MeshPrepMessage = { ...result, bvh };
  const transfer: Transferable[] = [
    result.positions.buffer,
    result.normals.buffer,
    result.centroids.buffer,
    result.faceNormals.buffer,
    result.neighbours.buffer,
    ...bvh.roots,
  ];
  if (bvh.indirectBuffer) transfer.push(bvh.indirectBuffer.buffer);
  (self as unknown as Worker).postMessage(message, transfer);
};
