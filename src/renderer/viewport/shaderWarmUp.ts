// Compiles every shader of the viewport in parallel (KHR_parallel_shader_compile)
// before the first scan and body arrive. A program compiled on first use blocks
// the UI thread, on Direct3D often for more than 100 ms.

import * as THREE from 'three';

import { type DisplayContext, warmUpObjects } from './displayItems';

export async function warmUpShaders(
  renderer: THREE.WebGLRenderer,
  camera: THREE.Camera,
  scene: THREE.Scene,
  options: { materials: THREE.Material[]; display: DisplayContext },
): Promise<void> {
  // A single triangle with every attribute the scan shaders read.
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(new Int16Array(12), 4, true));
  geometry.setAttribute('aFlags', new THREE.BufferAttribute(new Uint8Array(3), 1, true));
  const group = new THREE.Group();
  for (const material of options.materials) group.add(new THREE.Mesh(geometry, material));
  const samples = warmUpObjects(options.display);
  samples.forEach((sample) => group.add(sample.object));
  try {
    // The scene provides the lights, which are part of every lit program.
    await renderer.compileAsync(group, camera, scene);
  } finally {
    geometry.dispose();
    samples.forEach((sample) => sample.dispose());
  }
}
