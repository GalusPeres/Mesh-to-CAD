// The axis triad (docs/DESIGN.md 6.7): 48 px in the bottom left corner, X/Y/Z in
// the axis colours with 12 px labels, drawn into a scissored corner.

import * as THREE from 'three';

import type { DepthBias } from './depthBias';
import { createLines } from './displayItems';
import type { ThemeColors } from './displayItems';
import { SCENE_COLORS } from './palette';

export const AXIS_TRIAD_PX = 48;
const LABEL_PX = 12;
const FRUSTUM = 1.45;
const LABEL_TEXTURE_PX = 64;

const AXES = [
  { name: 'X', direction: new THREE.Vector3(1, 0, 0), color: SCENE_COLORS.axisX },
  { name: 'Y', direction: new THREE.Vector3(0, 1, 0), color: SCENE_COLORS.axisY },
  { name: 'Z', direction: new THREE.Vector3(0, 0, 1), color: SCENE_COLORS.axisZ },
] as const;

export class AxisTriad {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.OrthographicCamera(-FRUSTUM, FRUSTUM, FRUSTUM, -FRUSTUM, 0.1, 10);
  private readonly sprites: THREE.Sprite[] = [];

  constructor(
    bias: DepthBias,
    private theme: ThemeColors,
  ) {
    for (const axis of AXES) {
      const segment = new Float32Array([0, 0, 0, ...axis.direction.toArray()]);
      this.scene.add(createLines(segment, 2, axis.color, bias, 0).object);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ depthTest: false }));
      sprite.position.copy(axis.direction).multiplyScalar(1.22);
      // Sprite size in world units for a 12 px label in the 48 px square.
      const unitsPerPx = (2 * FRUSTUM) / AXIS_TRIAD_PX;
      sprite.scale.setScalar((LABEL_TEXTURE_PX / 4) * unitsPerPx);
      this.sprites.push(sprite);
      this.scene.add(sprite);
    }
    this.drawLabels();
  }

  static rect(height: number): { x: number; y: number; size: number } {
    return { x: 8, y: height - 8 - AXIS_TRIAD_PX, size: AXIS_TRIAD_PX };
  }

  setTheme(theme: ThemeColors): void {
    this.theme = theme;
    this.drawLabels();
  }

  follow(quaternion: THREE.Quaternion): void {
    const back = new THREE.Vector3(0, 0, 1).applyQuaternion(quaternion);
    this.camera.position.copy(back.multiplyScalar(4));
    this.camera.quaternion.copy(quaternion);
    this.camera.updateMatrixWorld();
  }

  dispose(): void {
    this.scene.traverse((node) => {
      const mesh = node as THREE.Mesh;
      mesh.geometry?.dispose();
      const material = mesh.material as THREE.SpriteMaterial | undefined;
      material?.map?.dispose();
      material?.dispose();
    });
  }

  private drawLabels(): void {
    if (typeof document === 'undefined') return;
    AXES.forEach((axis, index) => {
      const canvas = document.createElement('canvas');
      canvas.width = LABEL_TEXTURE_PX;
      canvas.height = LABEL_TEXTURE_PX;
      const context = canvas.getContext('2d');
      const sprite = this.sprites[index];
      if (!context || !sprite) return;
      // The sprite shows 16 CSS px; the texture has 4 texels per CSS px.
      context.font = `600 ${LABEL_PX * 4}px ${this.theme.font}`;
      context.fillStyle = axis.color;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(axis.name, LABEL_TEXTURE_PX / 2, LABEL_TEXTURE_PX / 2);
      sprite.material.map?.dispose();
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      sprite.material.map = texture;
      sprite.material.needsUpdate = true;
    });
  }
}
