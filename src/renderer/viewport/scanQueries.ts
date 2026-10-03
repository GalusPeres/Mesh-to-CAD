// Scan-face queries of the Viewport: brush circle, lasso polygon and topology.
// Owns the face-id pass that makes the visible-only variants possible.

import type * as THREE from 'three';

import type { ScanTopology, ScreenPoint } from './api';
import { FaceIdPass, type FaceIdView } from './faceIdPass';
import type { ScanMesh } from './scanMesh';
import { partCentroids, pickFacesInCircle } from './scanPicking';
import { type PickScene, pickViewOf } from './scenePicking';

export interface ScanQueryHost {
  /** The scan when it is drawn, else null. */
  visibleScan(): ScanMesh | null;
  scanMatrix: THREE.Matrix4;
  camera(): THREE.Camera;
  size(): { width: number; height: number };
  pickScene(): PickScene;
}

export class ScanQueries {
  readonly faceIds: FaceIdPass;
  private topology: { mesh: ScanMesh; matrix: THREE.Matrix4; value: Promise<ScanTopology> } | null =
    null;

  constructor(
    renderer: THREE.WebGLRenderer,
    clipping: THREE.Plane[],
    private readonly host: ScanQueryHost,
  ) {
    this.faceIds = new FaceIdPass(renderer, clipping);
  }

  /** The drawn faces changed; the id image is redrawn once the view has come to rest. */
  invalidateIds(): void {
    const scan = this.host.visibleScan();
    this.faceIds.invalidate(scan ? () => this.faceIdView(scan) : null);
  }

  /** The scan or its placement changed. */
  resetTopology(): void {
    this.topology = null;
  }

  circle(at: ScreenPoint, radius: number, visibleOnly: boolean): Uint32Array {
    const scan = this.host.visibleScan();
    if (!scan) return new Uint32Array();
    const start = performance.now();
    const image = visibleOnly ? this.faceIds.current(this.faceIdView(scan)) : null;
    const faces = pickFacesInCircle(scan, pickViewOf(this.host.pickScene()), at, radius, image);
    // Timings for tests/e2e/viewport-perf.spec.ts, recorded only in test mode.
    if (window.__m2cTest)
      performance.measure('viewport.brushSample', { start, end: performance.now() });
    return faces;
  }

  polygon(polygon: Float32Array, visibleOnly: boolean): Promise<Uint32Array> {
    const scan = this.host.visibleScan();
    if (!scan) return Promise.resolve(new Uint32Array());
    return scan.preparation.pickPolygon({
      polygon,
      view: pickViewOf(this.host.pickScene()),
      hidden: scan.hiddenMask(),
      image: visibleOnly ? this.faceIds.current(this.faceIdView(scan)) : null,
    });
  }

  /** Neighbours and part-coordinate centroids; computed once per scan and placement. */
  scanTopology(scan: ScanMesh | null): Promise<ScanTopology> {
    if (!scan) return Promise.reject(new Error('no scan loaded'));
    const cached = this.topology;
    if (cached?.mesh === scan && cached.matrix.equals(this.host.scanMatrix)) return cached.value;
    const matrix = this.host.scanMatrix.clone();
    const value = scan.preparation.topology.then((topology) => ({
      neighbours: topology.neighbours,
      centroids: partCentroids(topology.centroids, matrix),
    }));
    this.topology = { mesh: scan, matrix, value };
    return value;
  }

  dispose(): void {
    this.faceIds.dispose();
  }

  private faceIdView(scan: ScanMesh): FaceIdView {
    const { width, height } = this.host.size();
    const camera = this.host.camera();
    return { scan, scanMatrix: this.host.scanMatrix, camera, width, height };
  }
}
