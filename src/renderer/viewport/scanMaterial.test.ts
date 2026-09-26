import * as THREE from 'three';
import { describe, expect, it } from 'vitest';

import { bandIndex, deviationBands } from '../lib/deviationBands';
import {
  REGION_TEXTURE_SIZE,
  createScanMaterials,
  createScanUniforms,
  deviationBoundaries,
  deviationTextureData,
  writeRegionColors,
} from './scanMaterial';

// docs/DESIGN.md 6.6, from far below to far above, then "no data".
const DESIGN_BANDS = {
  standard: [
    '1E2F66',
    '2E56B8',
    '3C8DDB',
    '5CC3D6',
    '4DAF63',
    'E6CF4F',
    'EC9A3A',
    'D24B35',
    '7A1F14',
    '8C9096',
  ],
  colorBlind: [
    '08306B',
    '2166AC',
    '4393C3',
    '92C5DE',
    'E3E3E3',
    'F4A582',
    'D6604D',
    'B2182B',
    '67001F',
    '8C9096',
  ],
};

const texel = (data: Uint8Array, index: number) =>
  Array.from(data.subarray(index * 4, index * 4 + 3), (byte) => byte.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase();

describe('deviation colour texture', () => {
  it('holds the band tables of the design, one row per scheme', () => {
    const data = deviationTextureData();
    expect(data).toHaveLength(10 * 2 * 4);
    DESIGN_BANDS.standard.forEach((hex, band) => expect(texel(data, band)).toBe(hex));
    DESIGN_BANDS.colorBlind.forEach((hex, band) => expect(texel(data, 10 + band)).toBe(hex));
  });

  it('bands values exactly like lib/deviationBands', () => {
    const tolerance = 0.1;
    const range = 0.5;
    const boundaries = Array.from(deviationBoundaries(tolerance, range));
    const bands = deviationBands(tolerance, range);
    // The shader counts the boundaries a value reaches.
    const shaderBand = (value: number) =>
      boundaries.reduce((count, boundary) => count + (value >= boundary ? 1 : 0), 0);
    // Values exactly on a boundary may round either way in float32; stay just beside them.
    const values = [-9, -0.5001, -0.34, -0.2, -0.1001, -0.0999, 0, 0.0999, 0.1001, 0.34, 0.5001, 9];
    for (const value of values) {
      expect(shaderBand(Math.fround(value)), String(value)).toBe(
        bandIndex(Math.fround(value), bands),
      );
    }
  });
});

describe('region colour texture', () => {
  it('maps labels to palette colours and leaves label 0 transparent', () => {
    const data = new Uint8Array(REGION_TEXTURE_SIZE * REGION_TEXTURE_SIZE * 4);
    const colorIndex = new Uint8Array(300);
    colorIndex[1] = 0;
    colorIndex[2] = 9;
    colorIndex[299] = 12;
    writeRegionColors(data, colorIndex);
    expect(data[3]).toBe(0);
    expect(texel(data, 1)).toBe('C87979');
    expect(texel(data, 2)).toBe('F2A3C1');
    // Palette indices wrap; label 299 lives in the second texture row.
    expect(texel(data, 299)).toBe('A59145');
    expect(data[299 * 4 + 3]).toBe(255);
  });
});

describe('scan materials', () => {
  it('patch every shader chunk they rely on', () => {
    const uniforms = createScanUniforms();
    const { opaque, transparent } = createScanMaterials(uniforms, [new THREE.Plane()]);
    const shader = {
      uniforms: {},
      vertexShader: THREE.ShaderLib.physical.vertexShader,
      fragmentShader: THREE.ShaderLib.physical.fragmentShader,
    } as unknown as THREE.WebGLProgramParametersWithUniforms;
    opaque.onBeforeCompile(shader, {} as THREE.WebGLRenderer);
    expect(shader.vertexShader).toContain('gl_VertexID % 3');
    expect(shader.fragmentShader).toContain('uDeviationColors');
    expect(Object.keys(shader.uniforms)).toContain('uBounds');
    expect(transparent.transparent).toBe(true);
    expect(transparent.depthWrite).toBe(false);
    expect(opaque.customProgramCacheKey()).toBe(transparent.customProgramCacheKey());
  });
});
