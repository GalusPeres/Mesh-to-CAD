// The scan as a non-indexed mesh: face i owns vertices 3i..3i+2. WebGL 2 has no
// gl_PrimitiveID, so per-face state (selection, hover, hidden, pass/fail) is a
// per-vertex attribute; de-indexing makes it exact and keeps the face index of a
// ray hit identical to the kernel's face index. The heavy preparation (de-index,
// centroids, adjacency, BVH) happens in workers/meshPrep.worker.ts.

import * as THREE from 'three';
import { MeshBVH, acceleratedRaycast } from 'three-mesh-bvh';

import type { ScanPayload } from '@shared/protocol/generated/document-display';

import { type DeviationBand, bandIndex, deviationBands } from '../lib/deviationBands';
import type { DisplayMode } from '../state/viewStore';
import type { DeviationDisplay, ScanView } from './api';
import { DEVIATION_COLORS, REGION_PALETTE, SCENE_COLORS, SCENE_MIX } from './palette';
import type { MeshPrepMessage } from './workers/meshPrep.worker';

export const FLAG_SELECTED = 1;
export const FLAG_HOVER = 2;
export const FLAG_HIDDEN = 4;
const STATE_SHIFT = 3;
const STATE_MASK = 3 << STATE_SHIFT;

/** Triangle edges are drawn only below this face count (docs/DESIGN.md 6.2). */
export const EDGE_DISPLAY_LIMIT = 500_000;
const EDGE_ALPHA = 0.12;

function patchMaterial(material: THREE.MeshStandardMaterial): void {
  const color = (hex: string) => new THREE.Color(hex);
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, {
      uSelection: { value: color(SCENE_COLORS.selection) },
      uBackFace: { value: color(SCENE_COLORS.scanBackFace) },
      uPass: { value: color(SCENE_COLORS.pass) },
      uFail: { value: color(SCENE_COLORS.fail) },
      uFailFar: { value: color(SCENE_COLORS.failFar) },
    });
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        '#include <common>\nattribute float aFlags;\nvarying float vFlags;',
      )
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvFlags = aFlags;');
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        [
          '#include <common>',
          'varying float vFlags;',
          'uniform vec3 uSelection;',
          'uniform vec3 uBackFace;',
          'uniform vec3 uPass;',
          'uniform vec3 uFail;',
          'uniform vec3 uFailFar;',
        ].join('\n'),
      )
      .replace(
        '#include <color_fragment>',
        [
          '#include <color_fragment>',
          'float flags = floor(vFlags + 0.5);',
          'if (mod(floor(flags / 4.0), 2.0) >= 1.0) discard;',
          'if (!gl_FrontFacing) diffuseColor.rgb = uBackFace;',
          'float faceState = mod(floor(flags / 8.0), 4.0);',
          `if (faceState == 1.0) diffuseColor.rgb = mix(diffuseColor.rgb, uPass, ${SCENE_MIX.passFail.toFixed(2)});`,
          `if (faceState == 2.0) diffuseColor.rgb = mix(diffuseColor.rgb, uFail, ${SCENE_MIX.passFail.toFixed(2)});`,
          `if (faceState == 3.0) diffuseColor.rgb = mix(diffuseColor.rgb, uFailFar, ${SCENE_MIX.passFail.toFixed(2)});`,
          `if (mod(flags, 2.0) >= 1.0) diffuseColor.rgb = mix(diffuseColor.rgb, uSelection, ${SCENE_MIX.selection.toFixed(2)});`,
          `else if (mod(floor(flags / 2.0), 2.0) >= 1.0) diffuseColor.rgb = mix(diffuseColor.rgb, uSelection, ${SCENE_MIX.hover.toFixed(2)});`,
        ].join('\n'),
      );
  };
}

type ColorSource = 'regions' | 'deviation';

/** The displayed scan and its per-face state. */
export class ScanMesh implements ScanView {
  readonly mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>;
  readonly faceCount: number;
  readonly scanKey: string;
  /** Face centroids in scan-local coordinates (relative to the scan origin). */
  readonly centroids: Float32Array;
  readonly faceNormals: Float32Array;
  /** (F, 3) neighbour face per edge, -1 at open or non-manifold edges. */
  readonly neighbours: Int32Array;
  private readonly positions: Float32Array;
  private readonly flags: Uint8Array;
  private readonly flagAttribute: THREE.BufferAttribute;
  private readonly indices: Uint32Array;
  private hovered: Uint32Array | null = null;
  private stateFaces: Uint32Array | null = null;
  private edges: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | null = null;
  private displayMode: DisplayMode = 'shaded';
  private opacity = 1;
  private readonly colors: Record<ColorSource, Float32Array | null> = {
    regions: null,
    deviation: null,
  };
  private lastColorSource: ColorSource | null = null;
  private deviationVisible = false;
  private edgeColor = '#000000';
  private fullUploadPending = true;

  constructor(
    payload: ScanPayload,
    prepared: MeshPrepMessage,
    scanKey: string,
    private readonly invalidate: () => void,
  ) {
    this.scanKey = scanKey;
    this.indices = payload.indices;
    this.faceCount = payload.indices.length / 3;
    this.positions = prepared.positions;
    this.centroids = prepared.centroids;
    this.faceNormals = prepared.faceNormals;
    this.neighbours = prepared.neighbours;

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(prepared.positions, 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(prepared.normals, 3));
    this.flags = new Uint8Array(this.faceCount * 3);
    this.flagAttribute = new THREE.BufferAttribute(this.flags, 1);
    this.flagAttribute.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute('aFlags', this.flagAttribute);
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    geometry.boundsTree = MeshBVH.deserialize(prepared.bvh, geometry, { setIndex: false });

    const material = new THREE.MeshStandardMaterial({
      color: SCENE_COLORS.scan,
      roughness: 0.55,
      metalness: 0,
      side: THREE.DoubleSide,
    });
    patchMaterial(material);
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.raycast = acceleratedRaycast;
    this.mesh.matrixAutoUpdate = false;
  }

  dispose(): void {
    this.mesh.geometry.boundsTree = undefined;
    this.mesh.geometry.dispose();
    this.mesh.material.dispose();
    this.edges?.material.dispose();
  }

  /** De-indexed corner positions in scan-local coordinates (9 floats per face). */
  get cornerPositions(): Float32Array {
    return this.positions;
  }

  isHidden(face: number): boolean {
    return ((this.flags[face * 3] ?? 0) & FLAG_HIDDEN) !== 0;
  }

  /** Bounds of the selected faces in scan-local coordinates, or null without selection. */
  selectionBounds(): THREE.Box3 | null {
    const box = new THREE.Box3();
    const point = new THREE.Vector3();
    for (let face = 0; face < this.faceCount; face += 1) {
      if (((this.flags[face * 3] ?? 0) & (FLAG_SELECTED | FLAG_HIDDEN)) !== FLAG_SELECTED)
        continue;
      for (let corner = 0; corner < 3; corner += 1)
        box.expandByPoint(point.fromArray(this.positions, face * 9 + corner * 3));
    }
    return box.isEmpty() ? null : box;
  }

  setDisplayMode(mode: DisplayMode, deviationVisible: boolean, edgeColor: string): void {
    this.displayMode = mode;
    this.deviationVisible = deviationVisible;
    this.edgeColor = edgeColor;
    const material = this.mesh.material;
    const flat = mode === 'flat';
    if (material.flatShading !== flat) {
      material.flatShading = flat;
      material.needsUpdate = true;
    }
    this.updateEdges();
    this.updateOpacity();
    this.updateColors();
  }

  setClipping(planes: THREE.Plane[]): void {
    this.mesh.material.clippingPlanes = planes;
    if (this.edges) this.edges.material.clippingPlanes = planes;
    this.invalidate();
  }

  setSelection(mask: Uint8Array): void {
    for (let face = 0; face < this.faceCount; face += 1)
      this.setFlag(face, FLAG_SELECTED, (mask[face] ?? 0) !== 0);
    this.commitFlags();
  }

  updateSelection(faces: Uint32Array, selected: boolean): void {
    let first = Number.POSITIVE_INFINITY;
    let last = -1;
    for (const face of faces) {
      this.setFlag(face, FLAG_SELECTED, selected);
      if (face < first) first = face;
      if (face > last) last = face;
    }
    // Only the touched range goes to the GPU (brush strokes on large scans).
    this.commitFlags(last >= 0 ? [first, last] : null);
  }

  setHover(faces: Uint32Array | null): void {
    for (const face of this.hovered ?? []) this.setFlag(face, FLAG_HOVER, false);
    for (const face of faces ?? []) this.setFlag(face, FLAG_HOVER, true);
    this.hovered = faces;
    this.commitFlags();
  }

  setHidden(mask: Uint8Array | null): void {
    for (let face = 0; face < this.faceCount; face += 1)
      this.setFlag(face, FLAG_HIDDEN, !!mask && (mask[face] ?? 0) !== 0);
    this.commitFlags();
  }

  setFaceStates(faces: Uint32Array | null, states?: Uint8Array): void {
    for (const face of this.stateFaces ?? []) this.setState(face, 0);
    faces?.forEach((face, index) => this.setState(face, states?.[index] ?? 0));
    this.stateFaces = faces;
    this.commitFlags();
  }

  setRegions(labels: Uint16Array | null, colorIndex: Uint8Array | null): void {
    if (!labels || !colorIndex) {
      this.setColorSource('regions', null);
      return;
    }
    const colors = REGION_PALETTE.map((hex) => new THREE.Color(hex));
    const base = new THREE.Color(SCENE_COLORS.scan);
    const buffer = new Float32Array(this.faceCount * 9);
    for (let face = 0; face < this.faceCount; face += 1) {
      const label = labels[face] ?? 0;
      const color =
        label === 0 ? base : (colors[(colorIndex[label] ?? 0) % colors.length] ?? base);
      for (let corner = 0; corner < 3; corner += 1) color.toArray(buffer, face * 9 + corner * 3);
    }
    this.setColorSource('regions', buffer);
  }

  setDeviation(values: Float32Array | null, display?: DeviationDisplay): void {
    if (!values || !display) {
      this.setColorSource('deviation', null);
      return;
    }
    const bands: DeviationBand[] = deviationBands(display.tolerance, display.range, display.scheme);
    const palette = DEVIATION_COLORS[display.scheme].map((hex) => new THREE.Color(hex));
    const buffer = new Float32Array(this.faceCount * 9);
    for (let corner = 0; corner < this.indices.length; corner += 1) {
      const value = values[this.indices[corner] ?? 0] ?? Number.NaN;
      const color = palette[bandIndex(value, bands)] ?? palette[0];
      color?.toArray(buffer, corner * 3);
    }
    this.setColorSource('deviation', buffer);
  }

  setOpacity(opacity: number): void {
    this.opacity = opacity;
    this.updateOpacity();
  }

  private setColorSource(source: ColorSource, colors: Float32Array | null): void {
    this.colors[source] = colors;
    if (colors) this.lastColorSource = source;
    else if (this.lastColorSource === source) this.lastColorSource = null;
    this.updateColors();
  }

  /** The display mode picks the colour map; otherwise the one set last is shown. */
  private activeColors(): Float32Array | null {
    if (this.displayMode === 'regions') return this.colors.regions;
    if (this.displayMode === 'deviation' || this.deviationVisible) return this.colors.deviation;
    return this.lastColorSource ? this.colors[this.lastColorSource] : null;
  }

  private updateColors(): void {
    const colors = this.activeColors();
    const geometry = this.mesh.geometry;
    const material = this.mesh.material;
    const current = geometry.getAttribute('color') as THREE.BufferAttribute | undefined;
    if (current?.array === colors && material.vertexColors === !!colors) return;
    if (colors) geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    else geometry.deleteAttribute('color');
    material.vertexColors = !!colors;
    if (colors) material.color.setRGB(1, 1, 1);
    else material.color.set(SCENE_COLORS.scan);
    material.needsUpdate = true;
    this.invalidate();
  }

  private updateOpacity(): void {
    const xray = this.displayMode === 'xray';
    const opacity = Math.min(this.opacity, xray ? SCENE_MIX.xrayOpacity : 1);
    const material = this.mesh.material;
    const transparent = opacity < 1;
    if (material.transparent !== transparent) material.needsUpdate = true;
    material.transparent = transparent;
    material.opacity = opacity;
    material.depthWrite = !transparent;
    this.invalidate();
  }

  private updateEdges(): void {
    const wanted = this.displayMode === 'shadedEdges' && this.faceCount < EDGE_DISPLAY_LIMIT;
    if (wanted && !this.edges) {
      const material = new THREE.MeshBasicMaterial({
        wireframe: true,
        transparent: true,
        opacity: EDGE_ALPHA,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
      });
      material.clippingPlanes = this.mesh.material.clippingPlanes;
      this.edges = new THREE.Mesh(this.mesh.geometry, material);
      this.edges.raycast = () => undefined;
      this.mesh.add(this.edges);
    }
    if (!wanted && this.edges) {
      this.mesh.remove(this.edges);
      this.edges.material.dispose();
      this.edges = null;
    }
    this.edges?.material.color.set(this.edgeColor);
    this.invalidate();
  }

  private setFlag(face: number, flag: number, on: boolean): void {
    const offset = face * 3;
    const current = this.flags[offset] ?? 0;
    const next = on ? current | flag : current & ~flag;
    this.flags[offset] = next;
    this.flags[offset + 1] = next;
    this.flags[offset + 2] = next;
  }

  private setState(face: number, state: number): void {
    const offset = face * 3;
    const next = ((this.flags[offset] ?? 0) & ~STATE_MASK) | ((state & 3) << STATE_SHIFT);
    this.flags[offset] = next;
    this.flags[offset + 1] = next;
    this.flags[offset + 2] = next;
  }

  /** Called after each frame: pending flag changes have reached the GPU. */
  afterRender(): void {
    this.fullUploadPending = false;
  }

  private commitFlags(range: [number, number] | null = null): void {
    // Ranges accumulate until the next frame; a full change since the last frame wins.
    if (!range || this.fullUploadPending) {
      this.flagAttribute.clearUpdateRanges();
      this.fullUploadPending = true;
    } else {
      this.flagAttribute.addUpdateRange(range[0] * 3, (range[1] - range[0] + 1) * 3);
    }
    this.flagAttribute.needsUpdate = true;
    this.invalidate();
  }
}
