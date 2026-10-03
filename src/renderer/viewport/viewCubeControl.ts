// Pointer handling of the view cube: hover lights a zone, a click turns the view
// to it, dragging with the left button orbits (useful on touchpads). It is asked
// before every tool, so a click on the cube never paints or picks.

import * as THREE from 'three';

import type { ScreenPoint, Vec3, ViewportPointerEvent } from './api';
import type { CameraRig } from './CameraRig';
import type { ChromeInteraction } from './PointerRouter';
import { ViewCube } from './viewCube';
import { zoneView } from './viewCubeMath';

/** A press that moves further than this is a drag, not a click. */
const CLICK_SLOP_PX = 3;

export interface ViewCubeHost {
  readonly rig: CameraRig;
  width(): number;
  setCursor(cursor: string | null): void;
  invalidate(): void;
}

export class ViewCubeControl implements ChromeInteraction {
  private press: { start: ScreenPoint; last: ScreenPoint; zone: Vec3; dragging: boolean } | null =
    null;
  private overCube = false;

  constructor(
    private readonly cube: ViewCube,
    private readonly host: ViewCubeHost,
  ) {}

  onPointerDown(event: ViewportPointerEvent): boolean {
    if (event.button !== 0) return false;
    const zone = this.zoneAt(event.screen);
    if (!zone) return false;
    this.press = { start: event.screen, last: event.screen, zone, dragging: false };
    return true;
  }

  onPointerMove(event: ViewportPointerEvent): boolean {
    const press = this.press;
    if (press) {
      const moved = Math.hypot(event.screen.x - press.start.x, event.screen.y - press.start.y);
      if (moved > CLICK_SLOP_PX) press.dragging = true;
      if (press.dragging) {
        this.host.rig.orbitBy(event.screen.x - press.last.x, event.screen.y - press.last.y);
        press.last = event.screen;
      }
      return true;
    }
    const zone = this.zoneAt(event.screen);
    this.hover(zone);
    return zone !== null;
  }

  onPointerUp(event: ViewportPointerEvent): boolean {
    const press = this.press;
    this.press = null;
    if (!press) return false;
    if (!press.dragging) {
      const { direction, up } = zoneView(press.zone);
      this.host.rig.setView(direction, up);
    }
    this.hover(this.zoneAt(event.screen));
    return true;
  }

  onPointerLeave(): void {
    this.hover(null);
  }

  private hover(zone: Vec3 | null): void {
    if (this.cube.setHover(zone)) this.host.invalidate();
    if (!!zone !== this.overCube) {
      this.overCube = !!zone;
      this.host.setCursor(zone ? 'pointer' : null);
    }
  }

  private zoneAt(at: ScreenPoint): Vec3 | null {
    const rect = ViewCube.rect(this.host.width());
    const x = (at.x - rect.x) / rect.size;
    const y = (at.y - rect.y) / rect.size;
    if (x < 0 || y < 0 || x > 1 || y > 1) return null;
    return this.cube.zoneAt(new THREE.Vector2(x * 2 - 1, 1 - y * 2));
  }
}
