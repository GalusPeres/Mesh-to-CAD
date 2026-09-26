// Runs the scan preparation in a worker; falls back to the UI thread where
// workers are unavailable (unit tests).

import { BufferAttribute, BufferGeometry } from 'three';
import { MeshBVH } from 'three-mesh-bvh';

import type { MeshPrepMessage } from './meshPrep.worker';
import { type MeshPrepInput, prepareMesh } from './meshPrep';

export async function prepareScan(input: MeshPrepInput): Promise<MeshPrepMessage> {
  if (typeof Worker === 'undefined') {
    const result = prepareMesh(input);
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(result.positions, 3));
    const bvh = MeshBVH.serialize(new MeshBVH(geometry, { indirect: true }));
    return { ...result, bvh };
  }
  const worker = new Worker(new URL('./meshPrep.worker.ts', import.meta.url), { type: 'module' });
  try {
    return await new Promise<MeshPrepMessage>((resolve, reject) => {
      worker.onmessage = (event: MessageEvent<MeshPrepMessage>) => resolve(event.data);
      worker.onerror = (event) => reject(new Error(event.message || 'mesh preparation failed'));
      // Copies: the payload stays usable by the caller (deviation colours use the indices).
      worker.postMessage(input);
    });
  } finally {
    worker.terminate();
  }
}
