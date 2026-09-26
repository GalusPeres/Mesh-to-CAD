// Depth bias in world units. Bodies, construction surfaces and lines are moved
// towards the camera along the view ray, so they win against the scan wherever
// they lie within the bias of it. Polygon offset cannot do this: it works in
// depth-buffer steps (far too small for a body 0.1 mm from the scan) and not at
// all for lines. Moving along the view ray keeps every point on the same pixel.

import type * as THREE from 'three';

import { injectAfter } from './scanMaterial';

export interface DepthBias {
  readonly uniform: THREE.IUniform<number>;
  /** Scale of the bias: 1 for bodies, less for items that sit on bodies. */
  apply(material: THREE.Material, scale?: number): void;
  applyToFatLines(material: THREE.ShaderMaterial, scale?: number): void;
}

const shift = (variable: string, scale: number) =>
  `${variable}.xyz += (isOrthographic ? vec3(0.0, 0.0, 1.0) : normalize(-${variable}.xyz)) * uDepthBias * ${scale.toFixed(3)};`;

export function createDepthBias(): DepthBias {
  const uniform = { value: 0 };
  return {
    uniform,
    apply(material, scale = 1) {
      const previous = material.onBeforeCompile.bind(material);
      material.onBeforeCompile = (shader, renderer) => {
        previous(shader, renderer);
        shader.uniforms.uDepthBias = uniform;
        let vertex = injectAfter(shader.vertexShader, 'common', 'uniform float uDepthBias;');
        vertex = injectAfter(
          vertex,
          'project_vertex',
          `${shift('mvPosition', scale)}\ngl_Position = projectionMatrix * mvPosition;`,
        );
        shader.vertexShader = vertex;
      };
      const key = material.customProgramCacheKey.bind(material);
      material.customProgramCacheKey = () => `${key()}|bias${scale}`;
    },
    applyToFatLines(material, scale = 1) {
      // LineMaterial computes both segment ends itself instead of using project_vertex.
      const anchor = 'vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );';
      if (!material.vertexShader.includes(anchor)) throw new Error('LineMaterial changed');
      material.uniforms.uDepthBias = uniform;
      material.vertexShader = material.vertexShader
        .replace('void main() {', 'uniform float uDepthBias;\nvoid main() {')
        .replace(anchor, `${anchor}\n${shift('start', scale)}\n${shift('end', scale)}`);
      material.needsUpdate = true;
    },
  };
}
