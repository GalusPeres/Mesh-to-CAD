// Drawing of the handles: fat lines with a 1 px outline in the app background,
// knobs and arrow heads that keep their size in pixels at every zoom. Everything
// is drawn without depth test in a scene rendered after the main one.

import * as THREE from 'three';

import type { Ray, ScreenPoint, Vec3, ViewportInteraction } from './api';
import type { DepthBias } from './depthBias';
import { createLines } from './displayItems';

export const KNOB_PX = 6;
const ARROW_HEAD_PX = 12;

export interface HandleColors {
  neutral: string;
  outline: string;
  accent: string;
}

export interface HandleHost {
  /** Drawn after the scene, without depth test. */
  readonly group: THREE.Object3D;
  readonly bias: DepthBias;
  addInteraction(interaction: ViewportInteraction): () => void;
  screenToRay(at: ScreenPoint): Ray;
  worldToScreen(point: Vec3): ScreenPoint | null;
  worldPerPixel(point: Vec3): number;
  colors(): HandleColors;
  /** Runs `update` before every frame (screen-constant sizes); returns the unsubscribe. */
  beforeFrame(update: () => void): () => void;
  invalidate(): void;
}

const vector = (value: Vec3) => new THREE.Vector3(value[0], value[1], value[2]);

/** Lines, knobs and arrow heads of one handle; knob sizes follow the zoom. */
export class HandleGraphics {
  private readonly scaled: { object: THREE.Object3D; at: Vec3; px: number }[] = [];

  constructor(
    private readonly root: THREE.Group,
    private readonly host: HandleHost,
  ) {}

  clear(): void {
    this.scaled.length = 0;
    for (const child of [...this.root.children]) {
      this.root.remove(child);
      child.traverse((node) => {
        const shape = node as THREE.Mesh;
        shape.geometry?.dispose();
        (shape.material as THREE.Material | undefined)?.dispose();
      });
    }
  }

  polyline(points: Vec3[], color: string, width: number, closed = false): void {
    const corners = closed ? [...points, points[0]!] : points;
    const segments = new Float32Array(Math.max(0, corners.length - 1) * 6);
    for (let i = 0; i + 1 < corners.length; i += 1) {
      segments.set(corners[i]!, i * 6);
      segments.set(corners[i + 1]!, i * 6 + 3);
    }
    if (segments.length === 0) return;
    const outline = createLines(segments, width + 2, this.host.colors().outline, this.host.bias, 0);
    const line = createLines(segments, Math.max(width, 1.01), color, this.host.bias, 0);
    this.add(outline.object, outline.material, 20);
    this.add(line.object, line.material, 21);
  }

  knob(at: Vec3, color: string): void {
    this.sphere(at, KNOB_PX + 1, this.host.colors().outline, 22);
    this.sphere(at, KNOB_PX, color, 23);
  }

  /** A cone of fixed screen size with its tip at `tip`, pointing along `direction`. */
  arrowHead(tip: Vec3, direction: Vec3, color: string): void {
    const geometry = new THREE.ConeGeometry(0.45, 1, 16).translate(0, -0.5, 0);
    const mesh = new THREE.Mesh(geometry, this.material(color));
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), vector(direction).normalize());
    this.place(mesh, tip, ARROW_HEAD_PX, 23);
  }

  /** Recompute world sizes from the current zoom. */
  rescale(): void {
    for (const { object, at, px } of this.scaled) {
      object.scale.setScalar(this.host.worldPerPixel(at) * px);
      object.updateMatrix();
    }
  }

  private sphere(at: Vec3, radiusPx: number, color: string, order: number): void {
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), this.material(color));
    this.place(mesh, at, radiusPx, order);
  }

  private place(mesh: THREE.Mesh, at: Vec3, px: number, order: number): void {
    mesh.position.set(...at);
    this.scaled.push({ object: mesh, at, px });
    this.add(mesh, mesh.material as THREE.Material, order);
    this.rescale();
  }

  private material(color: string): THREE.MeshBasicMaterial {
    return new THREE.MeshBasicMaterial({ color });
  }

  private add(object: THREE.Object3D, material: THREE.Material, order: number): void {
    material.depthTest = false;
    material.depthWrite = false;
    object.renderOrder = order;
    object.frustumCulled = false;
    this.root.add(object);
  }
}
