// The scan material: MeshStandardMaterial plus one shader chunk that reads the
// per-face attributes (docs/DESIGN.md 6.2-6.4, 6.6). aFlags (u8: bit 0 selected,
// 1 hover, 2 hidden, 3-4 pass/fail state), aRegion (u16 label, looked up in a
// 256 x 256 colour texture) and aDeviation (f32, banded through a 10 x 2 colour
// texture). Display modes and colour maps are uniforms, so switching them never
// recompiles a program or rebuilds geometry.

import * as THREE from 'three';

import { NO_DATA_COLOR_INDEX, deviationBands } from '../lib/deviationBands';
import {
  DEVIATION_COLORS,
  type DeviationScheme,
  REGION_PALETTE,
  SCENE_COLORS,
  SCENE_MIX,
} from './palette';

/** aDeviation value of a vertex without data; NaN is not reliable in shaders. */
export const NO_DEVIATION = 3.0e38;
export const DEVIATION_SCHEMES: readonly DeviationScheme[] = ['standard', 'colorBlind'];
const BAND_COUNT = NO_DATA_COLOR_INDEX + 1;
export const REGION_TEXTURE_SIZE = 256;

export function hexBytes(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

/** RGBA bytes of the deviation colour texture: one row per scheme, one texel per band. */
export function deviationTextureData(): Uint8Array {
  const data = new Uint8Array(BAND_COUNT * DEVIATION_SCHEMES.length * 4);
  DEVIATION_SCHEMES.forEach((scheme, row) => {
    // Band colours come from the shared band table; the values only pick the layout.
    const colors = deviationBands(1, 3, scheme).map((band) => band.color);
    colors.push(DEVIATION_COLORS[scheme][NO_DATA_COLOR_INDEX] ?? '');
    colors.forEach((color, band) => {
      data.set([...hexBytes(color), 255], (row * BAND_COUNT + band) * 4);
    });
  });
  return data;
}

/** The eight finite band boundaries, ascending; a value's band is the count of boundaries <= it. */
export function deviationBoundaries(tolerance: number, range: number): Float32Array {
  const bands = deviationBands(tolerance, range);
  return Float32Array.from(bands.slice(1).map((band) => band.from));
}

/** Region label -> colour texels (label 0 and labels without colour stay transparent). */
export function writeRegionColors(data: Uint8Array, colorIndex: Uint8Array): void {
  data.fill(0);
  const labels = Math.min(colorIndex.length, REGION_TEXTURE_SIZE * REGION_TEXTURE_SIZE);
  for (let label = 1; label < labels; label += 1) {
    const color = REGION_PALETTE[(colorIndex[label] ?? 0) % REGION_PALETTE.length] ?? '';
    data.set([...hexBytes(color), 255], label * 4);
  }
}

function colorTexture(data: Uint8Array, width: number, height: number): THREE.DataTexture {
  const texture = new THREE.DataTexture(data, width, height, THREE.RGBAFormat);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

export interface ScanUniforms {
  [name: string]: THREE.IUniform;
  uSelection: THREE.IUniform<THREE.Color>;
  uBackFace: THREE.IUniform<THREE.Color>;
  uPass: THREE.IUniform<THREE.Color>;
  uFail: THREE.IUniform<THREE.Color>;
  uFailFar: THREE.IUniform<THREE.Color>;
  uEdgeColor: THREE.IUniform<THREE.Color>;
  uEdges: THREE.IUniform<number>;
  uFlat: THREE.IUniform<number>;
  uRegionsOn: THREE.IUniform<number>;
  uRegionColors: THREE.IUniform<THREE.DataTexture>;
  uDeviationOn: THREE.IUniform<number>;
  uDeviationColors: THREE.IUniform<THREE.DataTexture>;
  uScheme: THREE.IUniform<number>;
  uBounds: THREE.IUniform<Float32Array>;
}

export function createScanUniforms(): ScanUniforms {
  const size = REGION_TEXTURE_SIZE;
  return {
    uSelection: { value: new THREE.Color(SCENE_COLORS.selection) },
    uBackFace: { value: new THREE.Color(SCENE_COLORS.scanBackFace) },
    uPass: { value: new THREE.Color(SCENE_COLORS.pass) },
    uFail: { value: new THREE.Color(SCENE_COLORS.fail) },
    uFailFar: { value: new THREE.Color(SCENE_COLORS.failFar) },
    uEdgeColor: { value: new THREE.Color() },
    uEdges: { value: 0 },
    uFlat: { value: 0 },
    uRegionsOn: { value: 0 },
    uRegionColors: { value: colorTexture(new Uint8Array(size * size * 4), size, size) },
    uDeviationOn: { value: 0 },
    uDeviationColors: {
      value: colorTexture(deviationTextureData(), BAND_COUNT, DEVIATION_SCHEMES.length),
    },
    uScheme: { value: 0 },
    uBounds: { value: deviationBoundaries(0.1, 0.3) },
  };
}

const mix = (value: number) => value.toFixed(2);

const VERTEX_DECLARATIONS = `
attribute float aFlags;
attribute float aRegion;
attribute float aDeviation;
flat varying float vFlags;
flat varying float vRegion;
varying float vDeviation;
varying vec3 vBary;
`;

const VERTEX_BODY = `
vFlags = aFlags;
vRegion = aRegion;
vDeviation = aDeviation;
int corner = gl_VertexID % 3;
vBary = vec3(corner == 0 ? 1.0 : 0.0, corner == 1 ? 1.0 : 0.0, corner == 2 ? 1.0 : 0.0);
`;

// Hidden faces: all three corners outside the clip volume, so the face is culled.
const VERTEX_HIDE = `
if (mod(floor(floor(aFlags * 255.0 + 0.5) / 4.0), 2.0) >= 1.0) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
`;

const FRAGMENT_DECLARATIONS = `
flat varying float vFlags;
flat varying float vRegion;
varying float vDeviation;
varying vec3 vBary;
uniform vec3 uSelection;
uniform vec3 uBackFace;
uniform vec3 uPass;
uniform vec3 uFail;
uniform vec3 uFailFar;
uniform vec3 uEdgeColor;
uniform float uEdges;
uniform float uFlat;
uniform float uRegionsOn;
uniform sampler2D uRegionColors;
uniform float uDeviationOn;
uniform sampler2D uDeviationColors;
uniform float uScheme;
uniform float uBounds[8];
`;

const FRAGMENT_COLOR = `
float faceFlags = floor(vFlags * 255.0 + 0.5);
if (uRegionsOn > 0.5) {
  float label = floor(vRegion * 65535.0 + 0.5);
  vec4 region = texelFetch(uRegionColors, ivec2(int(mod(label, 256.0)), int(label / 256.0)), 0);
  if (label > 0.5 && region.a > 0.5) diffuseColor.rgb = region.rgb;
}
if (uDeviationOn > 0.5) {
  int band = ${NO_DATA_COLOR_INDEX};
  if (vDeviation < 1.0e38) {
    band = 0;
    for (int i = 0; i < 8; i++) band += vDeviation >= uBounds[i] ? 1 : 0;
  }
  diffuseColor.rgb = texelFetch(uDeviationColors, ivec2(band, int(uScheme)), 0).rgb;
}
if (!gl_FrontFacing) diffuseColor.rgb = uBackFace;
float faceState = mod(floor(faceFlags / 8.0), 4.0);
if (faceState == 1.0) diffuseColor.rgb = mix(diffuseColor.rgb, uPass, ${mix(SCENE_MIX.passFail)});
if (faceState == 2.0) diffuseColor.rgb = mix(diffuseColor.rgb, uFail, ${mix(SCENE_MIX.passFail)});
if (faceState == 3.0) diffuseColor.rgb = mix(diffuseColor.rgb, uFailFar, ${mix(SCENE_MIX.passFail)});
if (mod(faceFlags, 2.0) >= 1.0) diffuseColor.rgb = mix(diffuseColor.rgb, uSelection, ${mix(SCENE_MIX.selection)});
else if (mod(floor(faceFlags / 2.0), 2.0) >= 1.0) diffuseColor.rgb = mix(diffuseColor.rgb, uSelection, ${mix(SCENE_MIX.hover)});
`;

const FRAGMENT_FLAT_NORMAL = `
if (uFlat > 0.5) {
  normal = normalize(cross(dFdx(vViewPosition), dFdy(vViewPosition)));
  nonPerturbedNormal = normal;
}
`;

const FRAGMENT_EDGES = `
if (uEdges > 0.5) {
  vec3 edgeWidth = fwidth(vBary);
  vec3 inside = smoothstep(vec3(0.0), edgeWidth * 1.2, vBary);
  float edge = 1.0 - min(min(inside.x, inside.y), inside.z);
  gl_FragColor.rgb = mix(gl_FragColor.rgb, uEdgeColor, edge * ${mix(SCENE_MIX.triangleEdges)});
}
`;

/** Replace `#include <name>` and fail loudly when three.js no longer has the chunk. */
export function injectAfter(source: string, chunk: string, code: string): string {
  const anchor = `#include <${chunk}>`;
  if (!source.includes(anchor)) throw new Error(`shader chunk ${chunk} not found`);
  return source.replace(anchor, `${anchor}\n${code}`);
}

function patchScanShader(shader: THREE.WebGLProgramParametersWithUniforms, uniforms: ScanUniforms) {
  Object.assign(shader.uniforms, uniforms);
  let vertex = injectAfter(shader.vertexShader, 'common', VERTEX_DECLARATIONS);
  vertex = injectAfter(vertex, 'begin_vertex', VERTEX_BODY);
  shader.vertexShader = injectAfter(vertex, 'project_vertex', VERTEX_HIDE);
  let fragment = injectAfter(shader.fragmentShader, 'common', FRAGMENT_DECLARATIONS);
  fragment = injectAfter(fragment, 'color_fragment', FRAGMENT_COLOR);
  fragment = injectAfter(fragment, 'normal_fragment_begin', FRAGMENT_FLAT_NORMAL);
  shader.fragmentShader = injectAfter(fragment, 'opaque_fragment', FRAGMENT_EDGES);
}

export interface ScanMaterials {
  opaque: THREE.MeshStandardMaterial;
  /** X-ray and ghosted scan (sketch mode): no depth writes. */
  transparent: THREE.MeshStandardMaterial;
}

/** Both variants share the uniforms; they differ only in blending and depth writes. */
export function createScanMaterials(
  uniforms: ScanUniforms,
  clipping: THREE.Plane[],
): ScanMaterials {
  const create = (transparent: boolean) => {
    const material = new THREE.MeshStandardMaterial({
      color: SCENE_COLORS.scan,
      roughness: 0.55,
      metalness: 0,
      side: THREE.DoubleSide,
      transparent,
      depthWrite: !transparent,
      opacity: transparent ? SCENE_MIX.xrayOpacity : 1,
    });
    material.clippingPlanes = clipping;
    material.onBeforeCompile = (shader) => patchScanShader(shader, uniforms);
    material.customProgramCacheKey = () => 'm2c-scan-1';
    return material;
  };
  return { opaque: create(false), transparent: create(true) };
}
