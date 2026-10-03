// The face-id pass for visible-only picking: the scan drawn into an RGBA8
// target with face index + 1 as colour (gl_VertexID / 3 is the face on the
// non-indexed geometry, plus the chunk's first face). The image is read back
// once per view, after the camera has come to rest or on the first pick; brush
// samples then look faces up on the CPU without touching the GPU.

import * as THREE from 'three';

import type { FaceIdImage } from './faceIds';
import type { ScanMesh } from './scanMesh';

const VERTEX = /* glsl */ `
#include <common>
#include <clipping_planes_pars_vertex>
attribute float aFlags;
uniform int uFaceOffset;
flat varying highp int vFace;
void main() {
  #include <begin_vertex>
  #include <project_vertex>
  #include <clipping_planes_vertex>
  vFace = gl_VertexID / 3 + uFaceOffset;
  if (mod(floor(floor(aFlags * 255.0 + 0.5) / 4.0), 2.0) >= 1.0) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
}
`;

const FRAGMENT = /* glsl */ `
#include <clipping_planes_pars_fragment>
flat varying highp int vFace;
void main() {
  #include <clipping_planes_fragment>
  int id = vFace + 1;
  gl_FragColor = vec4(float(id & 255), float((id >> 8) & 255), float((id >> 16) & 255), float((id >> 24) & 255)) / 255.0;
}
`;

/** Wait this long after the last view change before reading back in the background. */
const PREFETCH_DELAY_MS = 150;

export interface FaceIdView {
  scan: ScanMesh;
  scanMatrix: THREE.Matrix4;
  camera: THREE.Camera;
  width: number;
  height: number;
}

export class FaceIdPass {
  private readonly scene = new THREE.Scene();
  private readonly group = new THREE.Group();
  private readonly materials = new Map<number, THREE.ShaderMaterial>();
  private target: THREE.WebGLRenderTarget | null = null;
  private builtFor: ScanMesh | null = null;
  private builtChunks = 0;
  private version = 0;
  private image: FaceIdImage | null = null;
  private imageVersion = -1;
  private prefetchTimer = 0;

  constructor(
    private readonly renderer: THREE.WebGLRenderer,
    private readonly clipping: THREE.Plane[],
  ) {
    this.group.matrixAutoUpdate = false;
    this.scene.add(this.group);
  }

  /** The view or the visible faces changed; the image must be drawn again. */
  invalidate(view: (() => FaceIdView | null) | null = null): void {
    this.version += 1;
    window.clearTimeout(this.prefetchTimer);
    if (view) {
      this.prefetchTimer = window.setTimeout(() => void this.prefetch(view()), PREFETCH_DELAY_MS);
    }
  }

  /** The image of the current view, drawn and read synchronously when stale. */
  current(view: FaceIdView): FaceIdImage {
    if (this.image && this.imageVersion === this.version) return this.image;
    const { width, height } = this.draw(view);
    const bytes = new Uint8Array(width * height * 4);
    this.renderer.readRenderTargetPixels(this.target!, 0, 0, width, height, bytes);
    this.store(bytes, width, height, this.version);
    return this.image!;
  }

  dispose(): void {
    window.clearTimeout(this.prefetchTimer);
    this.target?.dispose();
    for (const material of this.materials.values()) material.dispose();
    this.group.clear();
  }

  private async prefetch(view: FaceIdView | null): Promise<void> {
    if (!view || (this.image && this.imageVersion === this.version)) return;
    const version = this.version;
    const { width, height } = this.draw(view);
    const bytes = new Uint8Array(width * height * 4);
    try {
      await this.renderer.readRenderTargetPixelsAsync(this.target!, 0, 0, width, height, bytes);
    } catch {
      return;
    }
    if (version === this.version) this.store(bytes, width, height, version);
  }

  private store(bytes: Uint8Array, width: number, height: number, version: number): void {
    this.image = { ids: new Uint32Array(bytes.buffer), width, height, scale: 1 };
    this.imageVersion = version;
  }

  private draw(view: FaceIdView): { width: number; height: number } {
    const width = Math.max(1, Math.floor(view.width));
    const height = Math.max(1, Math.floor(view.height));
    if (!this.target || this.target.width !== width || this.target.height !== height) {
      this.target?.dispose();
      this.target = new THREE.WebGLRenderTarget(width, height, {
        type: THREE.UnsignedByteType,
        format: THREE.RGBAFormat,
        minFilter: THREE.NearestFilter,
        magFilter: THREE.NearestFilter,
        generateMipmaps: false,
        depthBuffer: true,
      });
    }
    this.build(view.scan);
    this.group.matrix.copy(view.scanMatrix);
    this.group.matrixWorldNeedsUpdate = true;

    const renderer = this.renderer;
    const previousTarget = renderer.getRenderTarget();
    const previousColor = renderer.getClearColor(new THREE.Color());
    const previousAlpha = renderer.getClearAlpha();
    const autoClear = renderer.autoClear;
    renderer.setRenderTarget(this.target);
    renderer.setClearColor(0x000000, 0);
    renderer.autoClear = true;
    renderer.render(this.scene, view.camera);
    renderer.setRenderTarget(previousTarget);
    renderer.setClearColor(previousColor, previousAlpha);
    renderer.autoClear = autoClear;
    return { width, height };
  }

  /** The id material of the chunk starting at face `start` (one program for all). */
  material(start: number): THREE.ShaderMaterial {
    let material = this.materials.get(start);
    if (!material) {
      material = new THREE.ShaderMaterial({
        vertexShader: VERTEX,
        fragmentShader: FRAGMENT,
        uniforms: { uFaceOffset: { value: start } },
        side: THREE.DoubleSide,
        blending: THREE.NoBlending,
        clipping: true,
      });
      material.clippingPlanes = this.clipping;
      this.materials.set(start, material);
    }
    return material;
  }

  /** One id mesh per shown chunk, sharing the chunk's buffers. */
  private build(scan: ScanMesh): void {
    const shown = [...scan.chunkGeometries()];
    if (this.builtFor === scan && this.builtChunks === shown.length) return;
    this.group.clear();
    for (const { geometry, start } of shown) {
      const mesh = new THREE.Mesh(geometry, this.material(start));
      mesh.matrixAutoUpdate = false;
      this.group.add(mesh);
    }
    this.builtFor = scan;
    this.builtChunks = shown.length;
  }
}
