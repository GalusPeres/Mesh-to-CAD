// The workers of one displayed scan: the preparation worker (finished after two
// messages) and the polygon-picking worker (alive until the scan is replaced).
// Where workers are unavailable (unit tests) or failed to start, the same code
// runs on the UI thread.

import { BufferAttribute, BufferGeometry } from 'three';
import { MeshBVH, type SerializedBVH } from 'three-mesh-bvh';

import {
  type MeshPrepInput,
  type PreparedGeometry,
  type PreparedTopology,
  prepareGeometry,
  prepareTopology,
} from './meshPrep';
import type { MeshPrepReply, PolygonPickReply, PolygonPickRequest } from './messages';
import { type PolygonPickQuery, pickFacesInPolygon } from './polygonPick';

export interface PreparedScanTopology extends PreparedTopology {
  bvh: SerializedBVH;
  /** The scan's vertex indices, (F, 3); deviation values are given per vertex. */
  indices: Uint32Array;
}

export interface ScanPreparation {
  readonly geometry: Promise<PreparedGeometry>;
  readonly topology: Promise<PreparedScanTopology>;
  pickPolygon(query: PolygonPickQuery): Promise<Uint32Array>;
  dispose(): void;
}

/** A worker failed to load or crashed; the caller may retry on the UI thread. */
export class WorkerFailure extends Error {}

function prepareInThread(input: MeshPrepInput): ScanPreparation {
  const geometry = prepareGeometry(input);
  const topology = prepareTopology(geometry, input.indices, input.positions.length / 3);
  const bvhGeometry = new BufferGeometry();
  bvhGeometry.setAttribute('position', new BufferAttribute(geometry.positions, 3));
  const bvh = MeshBVH.serialize(new MeshBVH(bvhGeometry, { indirect: true }));
  return {
    geometry: Promise.resolve(geometry),
    topology: Promise.resolve({ ...topology, bvh, indices: input.indices }),
    pickPolygon: (query) =>
      Promise.resolve(pickFacesInPolygon(query, topology.centroids, topology.faceNormals)),
    dispose: () => undefined,
  };
}

class WorkerPreparation implements ScanPreparation {
  readonly geometry: Promise<PreparedGeometry>;
  readonly topology: Promise<PreparedScanTopology>;
  private readonly prep: Worker;
  private readonly picker: Worker;
  private readonly pending = new Map<
    number,
    { resolve(faces: Uint32Array): void; reject(error: Error): void }
  >();
  private nextId = 1;
  private failure: Error | null = null;

  constructor(input: MeshPrepInput) {
    this.prep = new Worker(new URL('./meshPrep.worker.ts', import.meta.url), { type: 'module' });
    this.picker = new Worker(new URL('./polygonPick.worker.ts', import.meta.url), {
      type: 'module',
    });
    const channel = new MessageChannel();
    this.picker.postMessage({ port: channel.port2 }, [channel.port2]);
    this.picker.onmessage = (event: MessageEvent<PolygonPickReply>) => this.onPicked(event.data);
    this.picker.onerror = (event) => this.fail(new WorkerFailure(event.message || 'picker failed'));

    let settleGeometry!: (geometry: PreparedGeometry) => void;
    let settleTopology!: (topology: PreparedScanTopology) => void;
    let rejectGeometry!: (error: Error) => void;
    let rejectTopology!: (error: Error) => void;
    this.geometry = new Promise((resolve, reject) => {
      settleGeometry = resolve;
      rejectGeometry = reject;
    });
    this.topology = new Promise((resolve, reject) => {
      settleTopology = resolve;
      rejectTopology = reject;
    });
    // Nobody may be waiting for the topology yet; avoid an unhandled rejection.
    this.topology.catch(() => undefined);

    const failPreparation = (error: Error) => {
      rejectGeometry(error);
      rejectTopology(error);
      this.prep.terminate();
    };
    this.prep.onerror = (event) =>
      failPreparation(new WorkerFailure(event.message || 'scan preparation failed'));
    this.prep.onmessage = (event: MessageEvent<MeshPrepReply>) => {
      const message = event.data;
      if (message.type === 'geometry') {
        settleGeometry(message);
      } else if (message.type === 'topology') {
        settleTopology(message);
        this.prep.terminate();
      } else {
        failPreparation(new Error(message.message));
      }
    };
    const buffers = new Set<ArrayBufferLike>([
      input.positions.buffer,
      input.normals.buffer,
      input.indices.buffer,
    ]);
    this.prep.postMessage({ ...input, pickPort: channel.port1 }, [
      ...(buffers as Set<ArrayBuffer>),
      channel.port1,
    ]);
  }

  pickPolygon(query: PolygonPickQuery): Promise<Uint32Array> {
    if (this.failure) return Promise.reject(this.failure);
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      const request: PolygonPickRequest = { id, query };
      this.picker.postMessage(request);
    });
  }

  dispose(): void {
    this.prep.terminate();
    this.picker.terminate();
    this.fail(new Error('scan replaced'));
  }

  private onPicked(reply: PolygonPickReply): void {
    const request = this.pending.get(reply.id);
    this.pending.delete(reply.id);
    if (!request) return;
    if (reply.faces) request.resolve(reply.faces);
    else request.reject(new Error(reply.error ?? 'polygon picking failed'));
  }

  private fail(error: Error): void {
    this.failure = error;
    for (const request of this.pending.values()) request.reject(error);
    this.pending.clear();
  }
}

export function prepareScan(
  input: MeshPrepInput,
  options: { inThread?: boolean } = {},
): ScanPreparation {
  if (options.inThread || typeof Worker === 'undefined') return prepareInThread(input);
  return new WorkerPreparation(input);
}
