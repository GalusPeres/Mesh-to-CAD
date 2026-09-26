// The scan as a non-indexed mesh: face i owns vertices 3i..3i+2. WebGL 2 has no
// gl_PrimitiveID, so per-face state (selection, hover, hidden, pass/fail) is a
// per-vertex attribute; de-indexing makes it exact and keeps the face index of a
// ray hit identical to the kernel's face index.

import * as THREE from 'three';
import { MeshBVH, acceleratedRaycast } from 'three-mesh-bvh';

import type { ScanPayload } from '@shared/protocol/generated/document-display';

import { type DeviationBand, bandIndex, deviationBands } from '../lib/deviationBands';
import type { DeviationDisplay, ScanView } from './api';
import { DEVIATION_COLORS, REGION_PALETTE, SCENE_COLORS, SCENE_MIX } from './palette';

const FLAG_SELECTED = 1;
const FLAG_HOVER = 2;
const FLAG_HIDDEN = 4;
const STATE_SHIFT = 3;
const STATE_MASK = 3 << STATE_SHIFT;

/** Expand indexed arrays to one vertex per face corner. */
export function deIndex(source: Float32Array, indices: Uint32Array): Float32Array {
  const result = new Float32Array(indices.length * 3);
  for (let corner = 0; corner < indices.length; corner += 1) {
    const vertex = (indices[corner] ?? 0) * 3;
    result[corner * 3] = source[vertex] ?? 0;
    result[corner * 3 + 1] = source[vertex + 1] ?? 0;
    result[corner * 3 + 2] = source[vertex + 2] ?? 0;
  }
  return result;
}

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

/** The displayed scan and its per-face state. */
export class ScanMesh implements ScanView {
  readonly mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>;
  readonly faceCount: number;
  readonly scanKey: string;
  /** Face centroids in scan-local coordinates (relative to the scan origin). */
  readonly centroids: Float32Array;
  readonly faceNormals: Float32Array;
  private readonly flags: Uint8Array;
  private readonly flagAttribute: THREE.BufferAttribute;
  private readonly indices: Uint32Array;
  private hovered: Uint32Array | null = null;
  private stateFaces: Uint32Array | null = null;

  constructor(
    payload: ScanPayload,
    scanKey: string,
    private readonly invalidate: () => void,
  ) {
    this.scanKey = scanKey;
    this.indices = payload.indices;
    this.faceCount = payload.indices.length / 3;
    const geometry = new THREE.BufferGeometry();
    const positions = deIndex(payload.positions, payload.indices);
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute(
      'normal',
      new THREE.BufferAttribute(deIndex(payload.normals, payload.indices), 3),
    );
    this.flags = new Uint8Array(this.faceCount * 3);
    this.flagAttribute = new THREE.BufferAttribute(this.flags, 1);
    this.flagAttribute.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute('aFlags', this.flagAttribute);
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    geometry.boundsTree = new MeshBVH(geometry, { indirect: true });

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

    this.centroids = new Float32Array(this.faceCount * 3);
    this.faceNormals = new Float32Array(this.faceCount * 3);
    const a = new THREE.Vector3();
    const b = new THREE.Vector3();
    const c = new THREE.Vector3();
    for (let face = 0; face < this.faceCount; face += 1) {
      a.fromArray(positions, face * 9);
      b.fromArray(positions, face * 9 + 3);
      c.fromArray(positions, face * 9 + 6);
      this.centroids[face * 3] = (a.x + b.x + c.x) / 3;
      this.centroids[face * 3 + 1] = (a.y + b.y + c.y) / 3;
      this.centroids[face * 3 + 2] = (a.z + b.z + c.z) / 3;
      const normal = b.sub(a).cross(c.sub(a)).normalize();
      this.faceNormals.set([normal.x, normal.y, normal.z], face * 3);
    }
  }

  dispose(): void {
    this.mesh.geometry.boundsTree = undefined;
    this.mesh.geometry.dispose();
    this.mesh.material.dispose();
  }

  isHidden(face: number): boolean {
    return ((this.flags[face * 3] ?? 0) & FLAG_HIDDEN) !== 0;
  }

  setSelection(mask: Uint8Array): void {
    for (let face = 0; face < this.faceCount; face += 1)
      this.setFlag(face, FLAG_SELECTED, (mask[face] ?? 0) !== 0);
    this.commitFlags();
  }

  updateSelection(faces: Uint32Array, selected: boolean): void {
    for (const face of faces) this.setFlag(face, FLAG_SELECTED, selected);
    this.commitFlags();
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
      this.setOverlayColors(null);
      return;
    }
    const colors = REGION_PALETTE.map((hex) => new THREE.Color(hex));
    const base = new THREE.Color(SCENE_COLORS.scan);
    this.setOverlayColors((face) => {
      const label = labels[face] ?? 0;
      return label === 0 ? base : (colors[(colorIndex[label] ?? 0) % colors.length] ?? base);
    });
  }

  setDeviation(values: Float32Array | null, display?: DeviationDisplay): void {
    if (!values || !display) {
      this.setOverlayColors(null);
      return;
    }
    const bands: DeviationBand[] = deviationBands(display.tolerance, display.range, display.scheme);
    const palette = DEVIATION_COLORS[display.scheme].map((hex) => new THREE.Color(hex));
    const colors = new Float32Array(this.faceCount * 9);
    for (let corner = 0; corner < this.indices.length; corner += 1) {
      const value = values[this.indices[corner] ?? 0] ?? Number.NaN;
      const color = palette[bandIndex(value, bands)] ?? palette[0];
      color?.toArray(colors, corner * 3);
    }
    this.applyColors(colors);
  }

  setOpacity(opacity: number): void {
    const material = this.mesh.material;
    material.transparent = opacity < 1;
    material.opacity = opacity;
    material.depthWrite = opacity >= 1;
    material.needsUpdate = true;
    this.invalidate();
  }

  private setOverlayColors(colorOf: ((face: number) => THREE.Color) | null): void {
    if (!colorOf) {
      this.applyColors(null);
      return;
    }
    const colors = new Float32Array(this.faceCount * 9);
    for (let face = 0; face < this.faceCount; face += 1) {
      const color = colorOf(face);
      for (let corner = 0; corner < 3; corner += 1) color.toArray(colors, face * 9 + corner * 3);
    }
    this.applyColors(colors);
  }

  private applyColors(colors: Float32Array | null): void {
    const geometry = this.mesh.geometry;
    const material = this.mesh.material;
    if (colors) geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    else geometry.deleteAttribute('color');
    material.vertexColors = !!colors;
    if (colors) material.color.setRGB(1, 1, 1);
    else material.color.set(SCENE_COLORS.scan);
    material.needsUpdate = true;
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

  private commitFlags(): void {
    this.flagAttribute.needsUpdate = true;
    this.invalidate();
  }
}
