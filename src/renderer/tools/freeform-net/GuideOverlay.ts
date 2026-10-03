// Guides of building a net by hand, drawn over everything in the hover colour: the
// points clicked for a new face and the rubber band to the pointer, the edge under
// the pointer, and the row a dragged border edge will add.

import * as THREE from 'three';

import type { Overlay } from '../../viewport/api';
import { NET_COLORS } from '../../viewport/palette';

const POINT_SIZE_PX = 8;

export class GuideOverlay {
  private readonly lineGeometry = new THREE.BufferGeometry();
  private readonly pointGeometry = new THREE.BufferGeometry();
  private readonly lineMaterial = new THREE.LineBasicMaterial({
    color: NET_COLORS.hover,
    depthTest: false,
    transparent: true,
  });
  private readonly pointMaterial = new THREE.PointsMaterial({
    color: NET_COLORS.hover,
    size: POINT_SIZE_PX,
    sizeAttenuation: false,
    depthTest: false,
    transparent: true,
  });

  constructor(private readonly overlay: Overlay) {
    for (const object of [
      new THREE.LineSegments(this.lineGeometry, this.lineMaterial),
      new THREE.Points(this.pointGeometry, this.pointMaterial),
    ]) {
      object.frustumCulled = false;
      object.raycast = () => undefined;
      object.renderOrder = 30;
      overlay.add(object);
    }
    this.show([], []);
  }

  /** Line segments (x, y, z pairs) and points to draw; empty arrays clear them. */
  show(segments: readonly number[], points: readonly number[]): void {
    this.lineGeometry.setAttribute('position', new THREE.Float32BufferAttribute(segments, 3));
    this.pointGeometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
    this.lineGeometry.computeBoundingSphere();
    this.pointGeometry.computeBoundingSphere();
  }

  dispose(): void {
    this.overlay.dispose();
    this.lineGeometry.dispose();
    this.pointGeometry.dispose();
    this.lineMaterial.dispose();
    this.pointMaterial.dispose();
  }
}
