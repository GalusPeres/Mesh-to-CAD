// Turns a scan payload into a ScanMesh through the preparation worker. When a
// worker cannot start (for example a broken bundle), the payload is fetched
// again and prepared on the UI thread from then on: slower, but the scan shows.

import type * as THREE from 'three';

import type { SceneScan, ScenePayload } from '@shared/protocol/generated/document-display';

import type { PayloadFetcher } from './itemLayer';
import { ScanMesh } from './scanMesh';
import { type ScanPreparation, WorkerFailure, prepareScan } from './workers/scanWorkers';

let workersUnavailable = false;

function input(payload: ScenePayload | undefined) {
  if (payload?.type !== 'scan') throw new Error('scene payload is not a scan');
  return { positions: payload.positions, normals: payload.normals, indices: payload.indices };
}

export async function loadScanMesh(
  entry: SceneScan,
  payload: ScenePayload | undefined,
  fetch: PayloadFetcher,
  material: THREE.Material,
): Promise<ScanMesh> {
  let preparation: ScanPreparation = prepareScan(input(payload), { inThread: workersUnavailable });
  let geometry;
  try {
    geometry = await preparation.geometry;
  } catch (error) {
    if (!(error instanceof WorkerFailure) || workersUnavailable) throw error;
    workersUnavailable = true;
    window.m2c.app.log({
      level: 'warn',
      message: `scan preparation worker failed, preparing on the UI thread: ${error.message}`,
    });
    const [again] = await fetch([entry.key]);
    preparation = prepareScan(input(again), { inThread: true });
    geometry = await preparation.geometry;
  }
  return new ScanMesh(entry.key, entry.scanKey, geometry, preparation, material);
}
