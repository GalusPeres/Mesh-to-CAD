// Drag handles for tool parameters (docs/DESIGN.md 6.5): arrow (distance along a
// direction), plane (offset along a normal), arc (angle about an axis) and point
// (position in a plane). A handle is grabbed within 10 px of its knob with the
// left button and dragged without any key; Esc during a drag restores the value.
// Handles keep their on-screen size at every zoom and are drawn on top of the
// scene with a 1 px outline in the app background colour.

import * as THREE from 'three';

import type {
  ArcHandleOptions,
  ArrowHandleOptions,
  Handle,
  HandleEvents,
  HandleFactory,
  PlaneHandleOptions,
  PointHandleOptions,
  Ray,
  ScreenPoint,
  Vec3,
  ViewportInteraction,
} from './api';
import { type HandleColors, HandleGraphics, type HandleHost } from './handleGraphics';
import {
  angleAround,
  closestAlongAxis,
  distanceToSegment,
  intersectPlane,
  perpendicular,
  wrapDegrees,
} from './handleMath';
import { SCENE_COLORS } from './palette';

const GRAB_RADIUS_PX = 10;
const LINE_PX = 2;
const ARROW_PX = 48;
const GUIDE_DEGREES = 15;

export type { HandleColors, HandleHost } from './handleGraphics';

/** Internal options of the section plane gizmo; tools use the defaults. */
export interface HandleExtras {
  color?: (colors: HandleColors) => string;
  lineWidth?: number;
  /** Esc ended a drag; the value is back at its start. */
  onCancel?(): void;
}

const vector = (value: Vec3) => new THREE.Vector3(value[0], value[1], value[2]);
const tuple = (value: THREE.Vector3): Vec3 => [value.x, value.y, value.z];

function axisColor(direction: Vec3): string | null {
  const [x, y, z] = vector(direction).normalize().toArray().map(Math.abs) as [
    number,
    number,
    number,
  ];
  if (x > 0.999) return SCENE_COLORS.axisX;
  if (y > 0.999) return SCENE_COLORS.axisY;
  if (z > 0.999) return SCENE_COLORS.axisZ;
  return null;
}

type Value = number | Vec3;

abstract class BaseHandle<T extends Value> implements Handle {
  protected readonly root = new THREE.Group();
  protected readonly graphics: HandleGraphics;
  protected value: T;
  /** Geometry depends on the zoom (fixed-length arrows): redraw when it changes. */
  protected screenDependent = false;
  private drawnScale = 0;
  private state: 'idle' | 'hover' | 'drag' = 'idle';
  private grab: { start: T; at: T } | null = null;
  private readonly removeInteraction: () => void;
  private readonly removeFrameHook: () => void;

  constructor(
    protected readonly host: HandleHost,
    initial: T,
    private readonly events: HandleEvents,
    protected readonly extras: HandleExtras = {},
  ) {
    this.value = initial;
    this.graphics = new HandleGraphics(this.root, host);
    host.group.add(this.root);
    this.removeFrameHook = host.beforeFrame(() => this.beforeFrame());
    this.removeInteraction = host.addInteraction(this.interaction());
  }

  dispose(): void {
    this.removeInteraction();
    this.removeFrameHook();
    this.graphics.clear();
    this.host.group.remove(this.root);
    this.host.invalidate();
  }

  /** Draw again with the current colours (theme change). */
  refresh(): void {
    this.redraw();
  }

  protected abstract knob(): Vec3;
  /** The value the pointer ray points at, before the grab offset; null when undefined. */
  protected abstract valueAt(ray: Ray): T | null;
  protected abstract draw(color: string): void;

  protected baseColor(): string {
    return this.extras.color?.(this.host.colors()) ?? this.host.colors().neutral;
  }

  /** Pixel distance from the pointer to the grabbable parts of the handle. */
  protected grabDistance(at: ScreenPoint): number {
    const knob = this.host.worldToScreen(this.knob());
    return knob ? Math.hypot(knob.x - at.x, knob.y - at.y) : Infinity;
  }

  /** New value when dragging moved the pointer from `grabbed` to `now`. */
  protected combine(start: T, grabbed: T, now: T): T {
    if (typeof start === 'number') return (start + ((now as number) - (grabbed as number))) as T;
    const [s, g, n] = [start, grabbed, now] as [Vec3, Vec3, Vec3];
    const moved: Vec3 = [s[0] + n[0] - g[0], s[1] + n[1] - g[1], s[2] + n[2] - g[2]];
    return moved as unknown as T;
  }

  /** Called when a drag starts at `at` (before the first `combine`). */
  protected beginDrag(_at: T): void {}

  protected redraw(): void {
    this.drawnScale = this.host.worldPerPixel(this.knob());
    this.graphics.clear();
    this.draw(this.state === 'idle' ? this.baseColor() : SCENE_COLORS.activeHandle);
    this.host.invalidate();
  }

  private beforeFrame(): void {
    if (this.screenDependent) {
      const scale = this.host.worldPerPixel(this.knob());
      if (Math.abs(scale - this.drawnScale) > this.drawnScale * 0.01) this.redraw();
    }
    this.graphics.rescale();
  }

  private interaction(): ViewportInteraction {
    const rayValue = (screen: ScreenPoint) => this.valueAt(this.host.screenToRay(screen));
    return {
      onPointerDown: (event) => {
        if (event.button !== 0 || this.grabDistance(event.screen) > GRAB_RADIUS_PX) return false;
        const at = rayValue(event.screen);
        if (at === null) return false;
        this.grab = { start: this.value, at };
        this.beginDrag(at);
        this.state = 'drag';
        this.redraw();
        return true;
      },
      onPointerMove: (event) => {
        const grab = this.grab;
        if (this.state === 'drag' && grab) {
          const now = rayValue(event.screen);
          if (now !== null) {
            this.value = this.combine(grab.start, grab.at, now);
            this.redraw();
            this.events.onChange?.(this.value);
          }
          return true;
        }
        const near = this.grabDistance(event.screen) <= GRAB_RADIUS_PX;
        if (near !== (this.state === 'hover')) {
          this.state = near ? 'hover' : 'idle';
          this.redraw();
        }
        return false;
      },
      onPointerUp: () => {
        if (this.state !== 'drag') return false;
        this.state = 'hover';
        this.grab = null;
        this.redraw();
        this.events.onCommit?.(this.value);
        return true;
      },
      onKeyDown: (event) => {
        if (event.key !== 'Escape' || this.state !== 'drag' || !this.grab) return false;
        this.value = this.grab.start;
        this.grab = null;
        this.state = 'idle';
        this.redraw();
        this.events.onChange?.(this.value);
        this.extras.onCancel?.();
        return true;
      },
    };
  }
}

class ArrowHandle extends BaseHandle<number> {
  constructor(
    host: HandleHost,
    private readonly options: ArrowHandleOptions,
    extras?: HandleExtras,
  ) {
    super(host, options.value, options, extras);
    this.redraw();
  }

  protected override baseColor(): string {
    const axis = this.options.color === 'axis' ? axisColor(this.options.direction) : null;
    return axis ?? super.baseColor();
  }

  protected knob(): Vec3 {
    const direction = vector(this.options.direction).normalize();
    return tuple(vector(this.options.origin).addScaledVector(direction, this.value));
  }

  protected valueAt(ray: Ray): number | null {
    const t = closestAlongAxis(this.options.origin, this.options.direction, ray);
    return Number.isFinite(t) ? t : null;
  }

  protected draw(color: string): void {
    this.graphics.polyline(
      [this.options.origin, this.knob()],
      color,
      this.extras.lineWidth ?? LINE_PX,
    );
    const direction: Vec3 =
      this.value < 0 ? tuple(vector(this.options.direction).negate()) : this.options.direction;
    this.graphics.arrowHead(this.knob(), direction, color);
  }
}

class PlaneHandle extends BaseHandle<number> {
  private readonly normal: THREE.Vector3;
  private readonly x: THREE.Vector3;
  private readonly y: THREE.Vector3;

  constructor(
    host: HandleHost,
    private readonly options: PlaneHandleOptions,
    extras?: HandleExtras,
  ) {
    super(host, options.value, options, extras);
    this.screenDependent = true;
    this.normal = vector(options.normal).normalize();
    this.x = vector(options.xDirection).projectOnPlane(this.normal).normalize();
    if (this.x.lengthSq() < 0.5) this.x.set(...perpendicular(options.normal));
    this.y = this.normal.clone().cross(this.x);
    this.redraw();
  }

  private center(): THREE.Vector3 {
    return vector(this.options.origin).addScaledVector(this.normal, this.value);
  }

  private corners(): Vec3[] {
    const half = this.options.size / 2;
    const c = this.center();
    return [
      [half, half],
      [-half, half],
      [-half, -half],
      [half, -half],
    ].map(([u = 0, v = 0]) =>
      tuple(c.clone().addScaledVector(this.x, u).addScaledVector(this.y, v)),
    );
  }

  /** Tip of the normal arrow, a fixed number of pixels from the centre. */
  protected knob(): Vec3 {
    const c = this.center();
    return tuple(c.addScaledVector(this.normal, this.host.worldPerPixel(tuple(c)) * ARROW_PX));
  }

  protected override grabDistance(at: ScreenPoint): number {
    const corners = this.corners().map((corner) => this.host.worldToScreen(corner));
    let best = super.grabDistance(at);
    corners.forEach((corner, index) => {
      const next = corners[(index + 1) % corners.length];
      if (corner && next) best = Math.min(best, distanceToSegment(at, corner, next));
    });
    return best;
  }

  protected valueAt(ray: Ray): number | null {
    const t = closestAlongAxis(this.options.origin, this.options.normal, ray);
    return Number.isFinite(t) ? t : null;
  }

  protected draw(color: string): void {
    const width = this.extras.lineWidth ?? LINE_PX;
    this.graphics.polyline(this.corners(), color, width, true);
    const center = tuple(this.center());
    this.graphics.polyline([center, this.knob()], color, width);
    this.graphics.arrowHead(this.knob(), tuple(this.normal), color);
  }
}

class ArcHandle extends BaseHandle<number> {
  private lastAngle = 0;

  constructor(
    host: HandleHost,
    private readonly options: ArcHandleOptions,
    extras?: HandleExtras,
  ) {
    super(host, options.value, options, extras);
    this.redraw();
  }

  private pointAt(degrees: number): Vec3 {
    const axis = vector(this.options.axis).normalize();
    const x = vector(this.options.reference).projectOnPlane(axis).normalize();
    const y = axis.clone().cross(x);
    const angle = (degrees * Math.PI) / 180;
    return tuple(
      vector(this.options.center)
        .addScaledVector(x, Math.cos(angle) * this.options.radius)
        .addScaledVector(y, Math.sin(angle) * this.options.radius),
    );
  }

  private arc(from: number, to: number): Vec3[] {
    const steps = Math.max(2, Math.ceil(Math.abs(to - from) / 3));
    return Array.from({ length: steps + 1 }, (_, i) =>
      this.pointAt(from + ((to - from) * i) / steps),
    );
  }

  protected knob(): Vec3 {
    return this.pointAt(this.value);
  }

  protected valueAt(ray: Ray): number | null {
    const hit = intersectPlane(ray, this.options.center, this.options.axis);
    if (!hit) return null;
    return angleAround(hit, this.options.center, this.options.axis, this.options.reference);
  }

  protected override beginDrag(at: number): void {
    this.lastAngle = at;
  }

  /** Angles wrap at +-180 degrees; accumulate the wrapped steps so a drag can pass them. */
  protected override combine(_start: number, _grabbed: number, now: number): number {
    const step = wrapDegrees(now - this.lastAngle);
    this.lastAngle = now;
    return this.value + step;
  }

  protected draw(color: string): void {
    const width = this.extras.lineWidth ?? LINE_PX;
    if (Math.abs(this.value) > 0.5) this.graphics.polyline(this.arc(0, this.value), color, width);
    const guide = this.arc(this.value - GUIDE_DEGREES, this.value + GUIDE_DEGREES);
    this.graphics.polyline(guide, color, width);
    this.graphics.knob(this.knob(), color);
  }
}

class PointHandle extends BaseHandle<Vec3> {
  constructor(
    host: HandleHost,
    private readonly options: PointHandleOptions,
    extras?: HandleExtras,
  ) {
    super(host, options.position, options, extras);
    this.redraw();
  }

  protected knob(): Vec3 {
    return this.value;
  }

  protected valueAt(ray: Ray): Vec3 | null {
    return intersectPlane(ray, this.value, this.options.planeNormal);
  }

  protected draw(color: string): void {
    this.graphics.knob(this.value, color);
  }
}

export interface InternalHandleFactory extends HandleFactory {
  arrow(options: ArrowHandleOptions, extras?: HandleExtras): Handle;
  arc(options: ArcHandleOptions, extras?: HandleExtras): Handle;
  plane(options: PlaneHandleOptions, extras?: HandleExtras): Handle;
  point(options: PointHandleOptions, extras?: HandleExtras): Handle;
  /** Redraw every live handle (theme change). */
  refreshAll(): void;
}

export function createHandleFactory(host: HandleHost): InternalHandleFactory {
  const live = new Set<BaseHandle<Value>>();
  const track = <H extends BaseHandle<Value>>(handle: H): Handle => {
    live.add(handle);
    return {
      dispose: () => {
        live.delete(handle);
        handle.dispose();
      },
    };
  };
  return {
    arrow: (options, extras) => track(new ArrowHandle(host, options, extras)),
    plane: (options, extras) => track(new PlaneHandle(host, options, extras)),
    arc: (options, extras) => track(new ArcHandle(host, options, extras)),
    point: (options, extras) => track(new PointHandle(host, options, extras)),
    refreshAll: () => live.forEach((handle) => handle.refresh()),
  };
}
