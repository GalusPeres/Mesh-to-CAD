// Cameras and navigation: orthographic (default) and perspective cameras, the orbit
// controls, fitting and standard views. Z is up.

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import type { Projection } from '../state/viewStore';
import type { ScreenPoint, StandardView, Vec3 } from './api';
import {
  STANDARD_VIEWS,
  boxSphere,
  cameraPosition,
  orthographicHalfHeight,
  perspectiveDistance,
} from './cameraMath';
import { SCENE_COLORS } from './palette';

const FOV_DEG = 35;

export class CameraRig {
  private readonly orthographic = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10_000);
  private readonly perspective = new THREE.PerspectiveCamera(FOV_DEG, 1, 0.1, 10_000);
  private active: THREE.OrthographicCamera | THREE.PerspectiveCamera = this.orthographic;
  private controls: OrbitControls;
  private orthoHalfHeight = 100;
  private orbitLocked = false;
  private width = 1;
  private height = 1;

  constructor(
    scene: THREE.Scene,
    private readonly element: HTMLElement,
    private readonly onChange: () => void,
  ) {
    for (const camera of [this.orthographic, this.perspective]) {
      camera.up.set(0, 0, 1);
      camera.position.set(200, -200, 200);
      // A headlight attached to the camera shows scan detail from every direction.
      const headlight = new THREE.DirectionalLight(SCENE_COLORS.headlight, 1.4);
      headlight.position.set(-0.4, 0.6, 1);
      camera.add(headlight);
      scene.add(camera);
    }
    this.controls = this.createControls();
  }

  get camera(): THREE.Camera {
    return this.active;
  }

  get target(): Vec3 {
    return [this.controls.target.x, this.controls.target.y, this.controls.target.z];
  }

  /** Orbit controls react to the pointer only while enabled (not during tool drags). */
  setNavigationEnabled(enabled: boolean): void {
    this.controls.enabled = enabled;
  }

  setOrbitLocked(locked: boolean): void {
    this.orbitLocked = locked;
    this.controls.enableRotate = !locked;
  }

  dispose(): void {
    this.controls.dispose();
  }

  resize(width: number, height: number): void {
    this.width = Math.max(1, width);
    this.height = Math.max(1, height);
    this.updateProjection();
  }

  fitBox(min: Vec3, max: Vec3): void {
    const sphere = boxSphere(min, max);
    const aspect = this.width / this.height;
    this.orthoHalfHeight = orthographicHalfHeight(sphere.radius, aspect);
    const distance =
      this.active === this.perspective
        ? perspectiveDistance(sphere.radius, FOV_DEG, aspect) * 1.05
        : sphere.radius * 4;
    this.place(sphere.center, this.viewDirection(), distance, sphere.radius);
  }

  setStandardView(view: StandardView): void {
    const { direction, up } = STANDARD_VIEWS[view];
    this.active.up.set(...up);
    const distance = this.distance();
    this.place(this.target, direction, distance, distance / 4);
  }

  lookAlong(origin: Vec3, normal: Vec3, xDirection: Vec3): void {
    const n = new THREE.Vector3(...normal).normalize();
    this.active.up.copy(
      n
        .clone()
        .cross(new THREE.Vector3(...xDirection))
        .normalize(),
    );
    const distance = this.distance();
    this.place(origin, [-n.x, -n.y, -n.z], distance, distance / 4);
  }

  setProjection(projection: Projection): void {
    const next = projection === 'perspective' ? this.perspective : this.orthographic;
    if (next === this.active) return;
    const target = this.target;
    const direction = this.viewDirection();
    const distance = this.distance();
    next.up.copy(this.active.up);
    this.active = next;
    this.controls.dispose();
    this.controls = this.createControls();
    this.controls.enableRotate = !this.orbitLocked;
    this.place(target, direction, distance, distance / 4);
  }

  /** World units covered by one screen pixel at a point. */
  worldPerPixel(point: Vec3): number {
    if (this.active === this.orthographic) {
      return (
        (this.orthographic.top - this.orthographic.bottom) / this.orthographic.zoom / this.height
      );
    }
    const distance = this.perspective.position.distanceTo(new THREE.Vector3(...point));
    return (2 * distance * Math.tan((FOV_DEG * Math.PI) / 360)) / this.height;
  }

  toNdc(at: ScreenPoint): THREE.Vector2 {
    return new THREE.Vector2((at.x / this.width) * 2 - 1, -(at.y / this.height) * 2 + 1);
  }

  toScreen(point: Vec3): ScreenPoint | null {
    const projected = new THREE.Vector3(...point).project(this.active);
    if (projected.z > 1 || projected.z < -1) return null;
    return { x: ((projected.x + 1) / 2) * this.width, y: ((1 - projected.y) / 2) * this.height };
  }

  private place(target: Vec3, direction: Vec3, distance: number, radius: number): void {
    this.active.position.set(...cameraPosition(target, direction, distance));
    this.active.near = Math.max(distance - radius * 8, distance / 1000, 0.01);
    this.active.far = distance + radius * 8;
    this.controls.target.set(...target);
    this.updateProjection();
    this.controls.update();
    this.onChange();
  }

  private distance(): number {
    return this.active.position.distanceTo(this.controls.target);
  }

  private viewDirection(): Vec3 {
    const direction = new THREE.Vector3().subVectors(this.controls.target, this.active.position);
    if (direction.lengthSq() === 0) return STANDARD_VIEWS.iso.direction;
    direction.normalize();
    return [direction.x, direction.y, direction.z];
  }

  private updateProjection(): void {
    const aspect = this.width / this.height;
    this.perspective.aspect = aspect;
    this.perspective.updateProjectionMatrix();
    const half = this.orthoHalfHeight;
    Object.assign(this.orthographic, {
      left: -half * aspect,
      right: half * aspect,
      top: half,
      bottom: -half,
    });
    this.orthographic.updateProjectionMatrix();
  }

  private createControls(): OrbitControls {
    const controls = new OrbitControls(this.active, this.element);
    // The left button belongs to selection and tools; navigation uses right and middle.
    controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.ROTATE };
    controls.zoomToCursor = true;
    controls.enableDamping = false;
    controls.screenSpacePanning = true;
    controls.addEventListener('change', this.onChange);
    return controls;
  }
}
