// Cameras and navigation (docs/DESIGN.md 7.1): orthographic (default) and
// perspective cameras, right-drag orbit around the point under the cursor,
// middle or Shift+right drag pan, wheel zoom to the cursor, Ctrl+right drag zoom,
// fitting and standard views with 250 ms transitions. Z is up.

import * as THREE from 'three';

import type { Projection } from '../state/viewStore';
import type { ScreenPoint, StandardView, Vec3 } from './api';
import {
  STANDARD_VIEWS,
  TRANSITION_MS,
  boxSphere,
  easeOut,
  orthographicHalfHeight,
  perspectiveDistance,
} from './cameraMath';
import { SCENE_COLORS } from './palette';

const FOV_DEG = 35;
const ORBIT_RAD_PER_PX = 0.008;
const WHEEL_FACTOR = 0.0015;
const DRAG_ZOOM_FACTOR = 0.01;
const Z_UP = new THREE.Vector3(0, 0, 1);

type DragMode = 'orbit' | 'pan' | 'zoom';

interface CameraPose {
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
  target: THREE.Vector3;
  halfHeight: number;
}

export interface CameraRigOptions {
  /** Scan or body point under the cursor, the orbit pivot. */
  pickPivot(at: ScreenPoint): Vec3 | null;
  invertWheel(): boolean;
  onChange(): void;
}

/**
 * Rotate a camera pose around a pivot: yaw around world Z, then pitch around the
 * camera's right axis. The pivot keeps its place on the screen.
 */
export function orbitPose(pose: CameraPose, pivot: THREE.Vector3, yaw: number, pitch: number): void {
  const right = new THREE.Vector3(1, 0, 0).applyQuaternion(pose.quaternion);
  const rotation = new THREE.Quaternion()
    .setFromAxisAngle(Z_UP, yaw)
    .multiply(new THREE.Quaternion().setFromAxisAngle(right, pitch));
  pose.position.sub(pivot).applyQuaternion(rotation).add(pivot);
  pose.target.sub(pivot).applyQuaternion(rotation).add(pivot);
  pose.quaternion.premultiply(rotation).normalize();
}

/** Orientation of a camera looking in `direction` with `up` pointing up on screen. */
export function viewQuaternion(direction: Vec3, up: Vec3): THREE.Quaternion {
  const matrix = new THREE.Matrix4().lookAt(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(...direction),
    new THREE.Vector3(...up),
  );
  return new THREE.Quaternion().setFromRotationMatrix(matrix);
}

function reducedMotion(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

export class CameraRig {
  private readonly orthographic = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10_000);
  private readonly perspective = new THREE.PerspectiveCamera(FOV_DEG, 1, 0.1, 10_000);
  private active: THREE.OrthographicCamera | THREE.PerspectiveCamera = this.orthographic;
  private readonly targetPoint = new THREE.Vector3();
  private halfHeight = 100;
  private sceneCenter = new THREE.Vector3();
  private sceneRadius = 100;
  private orbitLocked = false;
  private navigationEnabled = true;
  private width = 1;
  private height = 1;
  private drag: {
    mode: DragMode;
    pointerId: number;
    last: ScreenPoint;
    start: ScreenPoint;
    pivot: THREE.Vector3;
  } | null = null;
  private animation = 0;
  private readonly detach: () => void;

  constructor(
    scene: THREE.Scene,
    private readonly element: HTMLElement,
    private readonly options: CameraRigOptions,
  ) {
    for (const camera of [this.orthographic, this.perspective]) {
      camera.up.set(0, 0, 1);
      // A headlight attached to the camera shows scan detail from every direction.
      const headlight = new THREE.DirectionalLight(SCENE_COLORS.headlight, 1.4);
      headlight.position.set(-0.4, 0.6, 1);
      camera.add(headlight);
      scene.add(camera);
    }
    this.applyPose({
      position: new THREE.Vector3(200, -200, 200),
      quaternion: viewQuaternion(STANDARD_VIEWS.iso.direction, STANDARD_VIEWS.iso.up),
      target: new THREE.Vector3(),
      halfHeight: 100,
    });

    const onPointerDown = (event: PointerEvent) => this.onPointerDown(event);
    const onPointerMove = (event: PointerEvent) => this.onPointerMove(event);
    const onPointerUp = (event: PointerEvent) => this.onPointerUp(event);
    const onWheel = (event: WheelEvent) => this.onWheel(event);
    element.addEventListener('pointerdown', onPointerDown);
    element.addEventListener('pointermove', onPointerMove);
    element.addEventListener('pointerup', onPointerUp);
    element.addEventListener('pointercancel', onPointerUp);
    element.addEventListener('wheel', onWheel, { passive: false });
    this.detach = () => {
      element.removeEventListener('pointerdown', onPointerDown);
      element.removeEventListener('pointermove', onPointerMove);
      element.removeEventListener('pointerup', onPointerUp);
      element.removeEventListener('pointercancel', onPointerUp);
      element.removeEventListener('wheel', onWheel);
    };
  }

  get camera(): THREE.OrthographicCamera | THREE.PerspectiveCamera {
    return this.active;
  }

  get target(): Vec3 {
    return [this.targetPoint.x, this.targetPoint.y, this.targetPoint.z];
  }

  /** Navigation reacts to the pointer only while enabled (not during tool drags). */
  setNavigationEnabled(enabled: boolean): void {
    this.navigationEnabled = enabled;
    if (!enabled) this.drag = null;
  }

  setOrbitLocked(locked: boolean): void {
    this.orbitLocked = locked;
  }

  /** Bounds of everything drawn; they set the clipping range and the fallback pivot. */
  setSceneBounds(center: Vec3, radius: number): void {
    this.sceneCenter.set(...center);
    this.sceneRadius = Math.max(radius, 1e-3);
    this.updateProjection();
  }

  dispose(): void {
    cancelAnimationFrame(this.animation);
    this.detach();
  }

  resize(width: number, height: number): void {
    this.width = Math.max(1, width);
    this.height = Math.max(1, height);
    this.updateProjection();
  }

  fitBox(min: Vec3, max: Vec3, animate = false): void {
    const sphere = boxSphere(min, max);
    const aspect = this.width / this.height;
    const halfHeight = orthographicHalfHeight(sphere.radius, aspect);
    const distance =
      this.active === this.perspective
        ? perspectiveDistance(sphere.radius, FOV_DEG, aspect) * 1.05
        : sphere.radius * 4;
    const target = new THREE.Vector3(...sphere.center);
    const forward = this.forward();
    this.goTo(
      {
        position: target.clone().addScaledVector(forward, -distance),
        quaternion: this.active.quaternion.clone(),
        target,
        halfHeight,
      },
      animate,
    );
  }

  setStandardView(view: StandardView): void {
    const { direction, up } = STANDARD_VIEWS[view];
    this.setView(direction, up);
  }

  /** Look in `direction` at the current target (standard views, view cube). */
  setView(direction: Vec3, up: Vec3, target: Vec3 = this.target): void {
    const distance = this.distance();
    const center = new THREE.Vector3(...target);
    this.goTo(
      {
        position: center.clone().addScaledVector(new THREE.Vector3(...direction).normalize(), -distance),
        quaternion: viewQuaternion(direction, up),
        target: center,
        halfHeight: this.halfHeight,
      },
      true,
    );
  }

  lookAlong(origin: Vec3, normal: Vec3, xDirection: Vec3): void {
    const n = new THREE.Vector3(...normal).normalize();
    const up = n.clone().cross(new THREE.Vector3(...xDirection)).normalize();
    this.setView([-n.x, -n.y, -n.z], [up.x, up.y, up.z], origin);
  }

  /** Rotate the view in the screen plane (view cube arrows). */
  roll(degrees: number): void {
    const rotation = new THREE.Quaternion().setFromAxisAngle(
      new THREE.Vector3(0, 0, 1),
      (degrees * Math.PI) / 180,
    );
    this.goTo(
      {
        position: this.active.position.clone(),
        quaternion: this.active.quaternion.clone().multiply(rotation),
        target: this.targetPoint.clone(),
        halfHeight: this.halfHeight,
      },
      true,
    );
  }

  /** Orbit around the target by a screen drag (view cube drag). */
  orbitBy(dx: number, dy: number): void {
    this.cancelAnimation();
    const pose = this.pose();
    orbitPose(pose, this.targetPoint.clone(), -dx * ORBIT_RAD_PER_PX, -dy * ORBIT_RAD_PER_PX);
    this.applyPose(pose);
  }

  setProjection(projection: Projection): void {
    const next = projection === 'perspective' ? this.perspective : this.orthographic;
    if (next === this.active) return;
    this.cancelAnimation();
    const tanHalf = Math.tan((FOV_DEG * Math.PI) / 360);
    const pose = this.pose();
    if (next === this.perspective) {
      // Keep the visible height at the target.
      const distance = this.halfHeight / tanHalf;
      pose.position.copy(this.targetPoint).addScaledVector(this.forward(), -distance);
    } else {
      pose.halfHeight = this.distance() * tanHalf;
      pose.position.copy(this.targetPoint).addScaledVector(this.forward(), -this.sceneRadius * 4);
    }
    this.active = next;
    this.applyPose(pose);
  }

  /** World units covered by one screen pixel at a point. */
  worldPerPixel(point: Vec3): number {
    if (this.active === this.orthographic) return (2 * this.halfHeight) / this.height;
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

  /** Zoom by `factor` (< 1 zooms in) keeping the point under the cursor in place. */
  zoomAt(at: ScreenPoint, factor: number): void {
    this.cancelAnimation();
    const ndc = this.toNdc(at);
    const pose = this.pose();
    if (this.active === this.orthographic) {
      const aspect = this.width / this.height;
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(pose.quaternion);
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(pose.quaternion);
      const shift = right
        .multiplyScalar(ndc.x * this.halfHeight * aspect * (1 - factor))
        .addScaledVector(up, ndc.y * this.halfHeight * (1 - factor));
      pose.position.add(shift);
      pose.target.add(shift);
      pose.halfHeight = Math.max(this.halfHeight * factor, 1e-4);
    } else {
      const ray = new THREE.Raycaster();
      ray.setFromCamera(ndc, this.perspective);
      const point = ray.ray.at(this.distance(), new THREE.Vector3());
      pose.position.lerp(point, 1 - factor);
      pose.target.lerp(point, 1 - factor);
    }
    this.applyPose(pose);
  }

  private onPointerDown(event: PointerEvent): void {
    if (!this.navigationEnabled || this.drag) return;
    let mode: DragMode | null = null;
    if (event.button === 1) mode = 'pan';
    if (event.button === 2) {
      if (event.ctrlKey) mode = 'zoom';
      else if (event.shiftKey || (this.orbitLocked && !event.altKey)) mode = 'pan';
      else mode = 'orbit';
    }
    if (!mode) return;
    this.cancelAnimation();
    const at = this.screenPoint(event);
    const pivot =
      mode === 'orbit' ? this.options.pickPivot(at) : null;
    this.drag = {
      mode,
      pointerId: event.pointerId,
      last: at,
      start: at,
      pivot: pivot ? new THREE.Vector3(...pivot) : this.sceneCenter.clone(),
    };
    this.element.setPointerCapture?.(event.pointerId);
  }

  private onPointerMove(event: PointerEvent): void {
    const drag = this.drag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    const at = this.screenPoint(event);
    const dx = at.x - drag.last.x;
    const dy = at.y - drag.last.y;
    drag.last = at;
    const pose = this.pose();
    if (drag.mode === 'orbit') {
      orbitPose(pose, drag.pivot, -dx * ORBIT_RAD_PER_PX, -dy * ORBIT_RAD_PER_PX);
      this.applyPose(pose);
    } else if (drag.mode === 'pan') {
      const perPixel = this.worldPerPixel(this.target);
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(pose.quaternion);
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(pose.quaternion);
      const shift = right.multiplyScalar(-dx * perPixel).addScaledVector(up, dy * perPixel);
      pose.position.add(shift);
      pose.target.add(shift);
      this.applyPose(pose);
    } else {
      this.zoomAt(drag.start, Math.exp(dy * DRAG_ZOOM_FACTOR));
    }
  }

  private onPointerUp(event: PointerEvent): void {
    if (this.drag?.pointerId !== event.pointerId) return;
    this.drag = null;
  }

  private onWheel(event: WheelEvent): void {
    if (!this.navigationEnabled) return;
    event.preventDefault();
    const sign = this.options.invertWheel() ? -1 : 1;
    const delta = event.deltaMode === 1 ? event.deltaY * 33 : event.deltaY;
    this.zoomAt(this.screenPoint(event), Math.exp(sign * delta * WHEEL_FACTOR));
  }

  private screenPoint(event: MouseEvent): ScreenPoint {
    const rect = this.element.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  private pose(): CameraPose {
    return {
      position: this.active.position.clone(),
      quaternion: this.active.quaternion.clone(),
      target: this.targetPoint.clone(),
      halfHeight: this.halfHeight,
    };
  }

  private goTo(goal: CameraPose, animate: boolean): void {
    this.cancelAnimation();
    if (!animate || reducedMotion()) {
      this.applyPose(goal);
      return;
    }
    const from = this.pose();
    const start = performance.now();
    const step = () => {
      const t = easeOut((performance.now() - start) / TRANSITION_MS);
      this.applyPose({
        position: from.position.clone().lerp(goal.position, t),
        quaternion: from.quaternion.clone().slerp(goal.quaternion, t),
        target: from.target.clone().lerp(goal.target, t),
        halfHeight: from.halfHeight + (goal.halfHeight - from.halfHeight) * t,
      });
      this.animation = t < 1 ? requestAnimationFrame(step) : 0;
    };
    this.animation = requestAnimationFrame(step);
  }

  private cancelAnimation(): void {
    cancelAnimationFrame(this.animation);
    this.animation = 0;
  }

  private applyPose(pose: CameraPose): void {
    for (const camera of [this.orthographic, this.perspective]) {
      camera.position.copy(pose.position);
      camera.quaternion.copy(pose.quaternion);
      camera.up.copy(new THREE.Vector3(0, 1, 0).applyQuaternion(pose.quaternion));
    }
    this.targetPoint.copy(pose.target);
    this.halfHeight = pose.halfHeight;
    this.updateProjection();
    this.options.onChange();
  }

  private distance(): number {
    return Math.max(this.active.position.distanceTo(this.targetPoint), 1e-3);
  }

  private forward(): THREE.Vector3 {
    return new THREE.Vector3(0, 0, -1).applyQuaternion(this.active.quaternion);
  }

  private updateProjection(): void {
    const aspect = this.width / this.height;
    // Depth range around the scene; orthographic cameras may use a negative near plane.
    const along = this.sceneCenter.clone().sub(this.active.position).dot(this.forward());
    const margin = this.sceneRadius * 4;
    this.perspective.aspect = aspect;
    this.perspective.near = Math.max(along - margin, this.sceneRadius * 1e-4, 1e-3);
    this.perspective.far = Math.max(along + margin, this.perspective.near * 10);
    this.perspective.updateProjectionMatrix();
    const half = this.halfHeight;
    Object.assign(this.orthographic, {
      left: -half * aspect,
      right: half * aspect,
      top: half,
      bottom: -half,
      near: along - margin,
      far: along + margin,
    });
    this.orthographic.updateProjectionMatrix();
    for (const camera of [this.orthographic, this.perspective]) camera.updateMatrixWorld();
  }
}
