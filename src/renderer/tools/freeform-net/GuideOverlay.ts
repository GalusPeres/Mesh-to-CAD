// Guides of building a net by hand, drawn over everything: in the hover colour the
// points clicked for a new face and the rubber band to the pointer, the edge under
// the pointer and the rows a drag will add; in the selection colour the chosen edges;
// in white the grips on the open border that can be dragged; big in the hover colour
// the points a dropped point will join.

import * as THREE from 'three';

import type { Overlay } from '../../viewport/api';
import { NET_COLORS, SCENE_COLORS } from '../../viewport/palette';

const POINT_SIZE_PX = 8;
const HANDLE_SIZE_PX = 9;
const JOIN_SIZE_PX = 16;

export interface Guides {
  /** Line segments, x, y, z per end. */
  segments: readonly number[];
  points: readonly number[];
  /** Chosen edges as segments. */
  chosen: readonly number[];
  /** Grips on the border that duplicate an edge. */
  handles: readonly number[];
  /** Points a dropped point will join. */
  joins: readonly number[];
}

const NONE: Guides = { segments: [], points: [], chosen: [], handles: [], joins: [] };

export class GuideOverlay {
  private readonly lineGeometry = new THREE.BufferGeometry();
  private readonly chosenGeometry = new THREE.BufferGeometry();
  private readonly pointGeometry = new THREE.BufferGeometry();
  private readonly handleGeometry = new THREE.BufferGeometry();
  private readonly joinGeometry = new THREE.BufferGeometry();
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
    new THREE.PointsMaterial({
      color: NET_COLORS.border,
      size: HANDLE_SIZE_PX,
      sizeAttenuation: false,
      depthTest: false,
      transparent: true,
    }),
    new THREE.PointsMaterial({
      color: NET_COLORS.hover,
      size: JOIN_SIZE_PX,
      sizeAttenuation: false,
      depthTest: false,
      transparent: true,
      opacity: 0.85,
    }),
  ];

  constructor(private readonly overlay: Overlay) {
    const [line, chosen, point, handle, join] = this.materials;
    for (const object of [
      new THREE.LineSegments(this.lineGeometry, line),
      new THREE.LineSegments(this.chosenGeometry, chosen),
      new THREE.Points(this.joinGeometry, join),
      new THREE.Points(this.handleGeometry, handle),
      new THREE.Points(this.pointGeometry, point),
    ]) {
      object.frustumCulled = false;
      object.raycast = () => undefined;
      object.renderOrder = 30;
      overlay.add(object);
    }
    this.show(NONE);
  }

  /** Draw these guides (empty arrays clear a kind). */
  show({ segments, points, chosen, handles, joins }: Guides): void {
    const set = (geometry: THREE.BufferGeometry, values: readonly number[]) => {
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(values, 3));
      geometry.computeBoundingSphere();
    };
    set(this.lineGeometry, segments);
    set(this.chosenGeometry, chosen);
    set(this.pointGeometry, points);
    set(this.handleGeometry, handles);
    set(this.joinGeometry, joins);
  }

  dispose(): void {
    this.overlay.dispose();
    this.lineGeometry.dispose();
    this.chosenGeometry.dispose();
    this.pointGeometry.dispose();
    this.handleGeometry.dispose();
    this.joinGeometry.dispose();
    this.materials.forEach((material) => material.dispose());
  }
}
