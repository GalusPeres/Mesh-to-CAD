// Overlays: groups of three.js objects that tools add to the scene and remove on
// dispose (viewport/api.ts `Overlay`).

import * as THREE from 'three';

import type { Overlay } from './api';
import type { DepthBias } from './depthBias';

export function createOverlayGroup(
  parent: THREE.Group,
  bias: DepthBias,
  invalidate: () => void,
): Overlay {
  const group = new THREE.Group();
  parent.add(group);
  return {
    add: (object) => {
      group.add(object as THREE.Object3D);
      invalidate();
    },
    clear: () => {
      group.clear();
      invalidate();
    },
    dispose: () => {
      parent.remove(group);
      invalidate();
    },
    applyDepthBias: (material, scale) => bias.apply(material as THREE.Material, scale),
  };
}
