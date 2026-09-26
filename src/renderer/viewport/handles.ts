// Drag handles for tool parameters: arrow (distance along a direction), plane
// (offset along a normal), arc (angle about an axis) and point (position in a plane).
// A handle is grabbed within 10 px of its knob; dragging reports values through
// onChange and the final value through onCommit.

import * as THREE from 'three';

import type {
  ArcHandleOptions,
  ArrowHandleOptions,
  Handle,
  HandleFactory,
  PlaneHandleOptions,
  PointHandleOptions,
  Ray,
  ScreenPoint,
  Vec3,
  ViewportInteraction,
} from './api';
import { SCENE_COLORS } from './palette';

const GRAB_RADIUS_PX = 10;
const KNOB_PX = 6;

export interface HandleHost {
  readonly group: THREE.Group;
  addInteraction(interaction: ViewportInteraction): () => void;
  screenToRay(at: ScreenPoint): Ray;
  worldToScreen(point: Vec3): ScreenPoint | null;
  /** World units covered by one screen pixel at a point. */
  worldPerPixel(point: Vec3): number;
  neutralColor(): string;
  invalidate(): void;
}

const vector = (value: Vec3) => new THREE.Vector3(value[0], value[1], value[2]);
const tuple = (value: THREE.Vector3): Vec3 => [value.x, value.y, value.z];

/** Parameter along `origin + t * direction` of the point closest to a ray. */
export function closestAlongAxis(origin: Vec3, direction: Vec3, ray: Ray): number {
  const d = vector(direction).normalize();
  const r = vector(ray.direction).normalize();
  const w = vector(origin).sub(vector(ray.origin));
  const b = d.dot(r);
  const denominator = 1 - b * b;
  if (Math.abs(denominator) < 1e-9) return 0;
  return (b * r.dot(w) - d.dot(w)) / denominator;
}

/** Intersection of a ray with a plane, or null when they are parallel. */
export function intersectPlane(ray: Ray, point: Vec3, normal: Vec3): Vec3 | null {
  const n = vector(normal).normalize();
  const direction = vector(ray.direction);
  const denominator = n.dot(direction);
  if (Math.abs(denominator) < 1e-9) return null;
  const t = n.dot(vector(point).sub(vector(ray.origin))) / denominator;
  return tuple(vector(ray.origin).addScaledVector(direction, t));
}

/** Angle in degrees of a point around an axis, measured from `reference`. */
export function angleAround(point: Vec3, center: Vec3, axis: Vec3, reference: Vec3): number {
  const a = vector(axis).normalize();
  const x = vector(reference).normalize();
  const y = a.clone().cross(x);
  const v = vector(point).sub(vector(center));
  return (Math.atan2(v.dot(y), v.dot(x)) * 180) / Math.PI;
}

function axisColor(direction: Vec3, fallback: string): string {
  const [x, y, z] = direction.map(Math.abs) as [number, number, number];
  if (x > 0.999) return SCENE_COLORS.axisX;
  if (y > 0.999) return SCENE_COLORS.axisY;
  if (z > 0.999) return SCENE_COLORS.axisZ;
  return fallback;
}

abstract class BaseHandle<T extends number | Vec3> implements Handle {
  protected readonly object = new THREE.Group();
  protected value: T;
  private dragging = false;
  private readonly removeInteraction: () => void;

  constructor(
    protected readonly host: HandleHost,
    initial: T,
    private readonly events: {
      onChange?(value: number | Vec3): void;
      onCommit?(value: number | Vec3): void;
    },
  ) {
    this.value = initial;
    host.group.add(this.object);
    this.removeInteraction = host.addInteraction({
      cursor: undefined,
      onPointerDown: (event) => {
        if (event.button !== 0 || !this.grabbed(event.screen)) return false;
        this.dragging = true;
        this.redraw(true);
        return true;
      },
      onPointerMove: (event) => {
        if (!this.dragging) return false;
        const next = this.valueFor(host.screenToRay(event.screen));
        if (next !== null) {
          this.value = next;
          this.redraw(true);
          this.events.onChange?.(next);
        }
        return true;
      },
      onPointerUp: () => {
        if (!this.dragging) return false;
        this.dragging = false;
        this.redraw(false);
        this.events.onCommit?.(this.value);
        return true;
      },
    });
  }

  dispose(): void {
    this.removeInteraction();
    this.clear();
    this.host.group.remove(this.object);
    this.host.invalidate();
  }

  protected abstract knob(): Vec3;
  protected abstract valueFor(ray: Ray): T | null;
  protected abstract draw(color: string): void;

  protected redraw(active = false): void {
    this.clear();
    this.draw(active ? SCENE_COLORS.activeHandle : this.color());
    this.host.invalidate();
  }

  protected color(): string {
    return this.host.neutralColor();
  }

  protected line(points: Vec3[], color: string): void {
    const geometry = new THREE.BufferGeometry().setFromPoints(points.map(vector));
    this.object.add(
      new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, depthTest: false })),
    );
  }

  protected dot(at: Vec3, color: string): void {
    const radius = this.host.worldPerPixel(at) * KNOB_PX;
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 12, 8),
      new THREE.MeshBasicMaterial({ color, depthTest: false }),
    );
    mesh.position.copy(vector(at));
    mesh.renderOrder = 10;
    this.object.add(mesh);
  }

  private grabbed(at: ScreenPoint): boolean {
    const knob = this.host.worldToScreen(this.knob());
    return !!knob && Math.hypot(knob.x - at.x, knob.y - at.y) <= GRAB_RADIUS_PX;
  }

  private clear(): void {
    for (const child of [...this.object.children]) {
      this.object.remove(child);
      if (child instanceof THREE.Mesh || child instanceof THREE.Line) {
        const shape = child as THREE.Mesh<THREE.BufferGeometry, THREE.Material>;
        shape.geometry.dispose();
        shape.material.dispose();
      }
    }
  }
}

class ArrowHandle extends BaseHandle<number> {
  constructor(
    host: HandleHost,
    private readonly options: ArrowHandleOptions,
  ) {
    super(host, options.value, options);
    this.redraw();
  }

  protected override color(): string {
    return this.options.color === 'axis'
      ? axisColor(this.options.direction, super.color())
      : super.color();
  }

  protected knob(): Vec3 {
    return tuple(
      vector(this.options.origin).addScaledVector(
        vector(this.options.direction).normalize(),
        this.value,
      ),
    );
  }

  protected valueFor(ray: Ray): number {
    return closestAlongAxis(this.options.origin, this.options.direction, ray);
  }

  protected draw(color: string): void {
    this.line([this.options.origin, this.knob()], color);
    this.dot(this.knob(), color);
  }
}

class PlaneHandle extends BaseHandle<number> {
  constructor(
    host: HandleHost,
    private readonly options: PlaneHandleOptions,
  ) {
    super(host, options.value, options);
    this.redraw();
  }

  protected knob(): Vec3 {
    return tuple(
      vector(this.options.origin).addScaledVector(
        vector(this.options.normal).normalize(),
        this.value,
      ),
    );
  }

  protected valueFor(ray: Ray): number {
    return closestAlongAxis(this.options.origin, this.options.normal, ray);
  }

  protected draw(color: string): void {
    const center = vector(this.knob());
    const x = vector(this.options.xDirection)
      .normalize()
      .multiplyScalar(this.options.size / 2);
    const y = vector(this.options.normal).normalize().cross(x.clone());
    const corners = [
      center.clone().add(x).add(y),
      center.clone().sub(x).add(y),
      center.clone().sub(x).sub(y),
      center.clone().add(x).sub(y),
    ];
    this.line([...corners, corners[0]!].map(tuple), color);
    this.dot(tuple(center), color);
  }
}

class ArcHandle extends BaseHandle<number> {
  constructor(
    host: HandleHost,
    private readonly options: ArcHandleOptions,
  ) {
    super(host, options.value, options);
    this.redraw();
  }

  private pointAt(angleDeg: number): Vec3 {
    const axis = vector(this.options.axis).normalize();
    const x = vector(this.options.reference).normalize();
    const y = axis.clone().cross(x);
    const angle = (angleDeg * Math.PI) / 180;
    return tuple(
      vector(this.options.center)
        .addScaledVector(x, Math.cos(angle) * this.options.radius)
        .addScaledVector(y, Math.sin(angle) * this.options.radius),
    );
  }

  protected knob(): Vec3 {
    return this.pointAt(this.value);
  }

  protected valueFor(ray: Ray): number | null {
    const hit = intersectPlane(ray, this.options.center, this.options.axis);
    return hit
      ? angleAround(hit, this.options.center, this.options.axis, this.options.reference)
      : null;
  }

  protected draw(color: string): void {
    const steps = 48;
    const points = Array.from({ length: steps + 1 }, (_, index) =>
      this.pointAt((this.value * index) / steps),
    );
    this.line(points, color);
    this.dot(this.knob(), color);
  }
}

class PointHandle extends BaseHandle<Vec3> {
  constructor(
    host: HandleHost,
    private readonly options: PointHandleOptions,
  ) {
    super(host, options.position, options);
    this.redraw();
  }

  protected knob(): Vec3 {
    return this.value;
  }

  protected valueFor(ray: Ray): Vec3 | null {
    return intersectPlane(ray, this.options.position, this.options.planeNormal);
  }

  protected draw(color: string): void {
    this.dot(this.value, color);
  }
}

export function createHandleFactory(host: HandleHost): HandleFactory {
  return {
    arrow: (options) => new ArrowHandle(host, options),
    plane: (options) => new PlaneHandle(host, options),
    arc: (options) => new ArcHandle(host, options),
    point: (options) => new PointHandle(host, options),
  };
}
