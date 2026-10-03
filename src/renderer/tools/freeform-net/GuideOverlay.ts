// Guides of building a net by hand, drawn over everything: in the hover colour the
// points clicked for a new face and the rubber band to the pointer, the edge under
// the pointer and the rows a drag will add; in the selection colour the chosen edges.

import * as THREE from 'three';

import type { Overlay } from '../../viewport/api';
import { NET_COLORS, SCENE_COLORS } from '../../viewport/palette';

const POINT_SIZE_PX = 8;

export class GuideOverlay {
  private readonly lineGeometry = new THREE.BufferGeometry();
  private readonly chosenGeometry = new THREE.BufferGeometry();
  private readonly pointGeometry = new THREE.BufferGeometry();
  private readonly materials: THREE.Material[] = [
    new THREE.LineBasicMaterial({ color: NET_COLORS.hover, depthTest: false, transparent: true }),
    new THREE.LineBasicMaterial({
      color: SCENE_COLORS.selection,
      depthTest: false,
      transparent: true,
    }),
    new THREE.PointsMaterial({
      color: NET_COLORS.hover,
      size: POINT_SIZE_PX,
      sizeAttenuation: false,
      depthTest: false,
      transparent: true,
    }),
  ];

  constructor(private readonly overlay: Overlay) {
    const [line, chosen, point] = this.materials;
    for (const object of [
      new THREE.LineSegments(this.lineGeometry, line),
      new THREE.LineSegments(this.chosenGeometry, chosen),
      new THREE.Points(this.pointGeometry, point),
    ]) {
      object.frustumCulled = false;
      object.raycast = () => undefined;
      object.renderOrder = 30;
      overlay.add(object);
    }
    this.show([], [], []);
  }

  /** Line segments (x, y, z pairs), points and chosen edges; empty arrays clear them. */
  show(segments: readonly number[], points: readonly number[], chosen: readonly number[]): void {
    const set = (geometry: THREE.BufferGeometry, values: readonly number[]) => {
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(values, 3));
      geometry.computeBoundingSphere();
    };
    set(this.lineGeometry, segments);
    set(this.chosenGeometry, chosen);
    set(this.pointGeometry, points);
  }

  dispose(): void {
    this.overlay.dispose();
    this.lineGeometry.dispose();
    this.chosenGeometry.dispose();
    this.pointGeometry.dispose();
    this.materials.forEach((material) => material.dispose());
  }
}
