// The net in the viewport: its dense limit surface, the overlay that draws it (surface,
// net lines, points) and its deviation from the scan as heatmap colours. NetEditor
// decides what to show; this keeps the viewport objects in step with it.

import type { LimitMapResult } from '@shared/protocol/generated/net';

import type { Vec3, Viewport } from '../../viewport/api';
import type { DeviationSummary } from './heatmap';
import { LimitSurface } from './limitSurface';
import { NetMeasure } from './netMeasure';
import { NetOverlay } from './NetOverlay';
import type { NetPoints } from './netPoints';

/** What is shown of the net: heatmap colours, and its points and lines. */
export interface NetLook {
  heatmap: boolean;
  netVisible: boolean;
}

export class NetScene {
  surface: LimitSurface | null = null;
  readonly measure: NetMeasure;
  private overlay: NetOverlay | null = null;

  constructor(
    private readonly viewport: Viewport,
    tolerance: number,
    private readonly look: () => NetLook,
  ) {
    this.measure = new NetMeasure(viewport, tolerance);
  }

  /** The quads changed: a new dense surface for the limit map, nothing measured yet. */
  replace(map: LimitMapResult, controlCount: number): LimitSurface {
    this.overlay?.dispose();
    this.surface = new LimitSurface(map, controlCount);
    this.overlay = new NetOverlay(this.viewport.createOverlay(), this.surface);
    this.overlay.setNetVisible(this.look().netVisible);
    this.measure.reset(this.surface);
    return this.surface;
  }

  /** No net (everything deleted): nothing to draw or measure. */
  clear(): void {
    this.measure.cancel();
    this.hide();
    this.surface = null;
    this.viewport.invalidate();
  }

  /** Draw the surface again after `hide`; false if there is none. */
  show(points: NetPoints): boolean {
    if (!this.surface) return false;
    this.overlay ??= new NetOverlay(this.viewport.createOverlay(), this.surface);
    this.overlay.positionsChanged();
    this.overlay.setNetVisible(this.look().netVisible);
    this.paint(points);
    return true;
  }

  /** Take the net out of the viewport; the surface is kept. */
  hide(): void {
    this.measure.cancel();
    this.overlay?.dispose();
    this.overlay = null;
  }

  /** The dense positions changed (the surface was evaluated anew). */
  positionsChanged(): void {
    this.overlay?.positionsChanged();
    this.viewport.invalidate();
  }

  /** Recompute positions, distances and colours of some dense vertices (during a drag). */
  refreshRows(vertices: Float64Array, rows: Uint32Array): void {
    const surface = this.surface;
    if (!surface) return;
    surface.evaluateRows(vertices, rows);
    this.measure.rows(surface, rows);
    this.overlay?.positionsChanged();
    if (this.look().heatmap) this.overlay?.setSurfaceColors(this.measure.colors);
    this.viewport.invalidate();
  }

  /** Measure every dense vertex against the scan, a chunk per frame. */
  async measureAll(): Promise<DeviationSummary | null> {
    const surface = this.surface;
    if (!surface) return null;
    return this.measure.all(surface, () => {
      if (this.look().heatmap) this.overlay?.setSurfaceColors(this.measure.colors);
      this.viewport.invalidate();
    });
  }

  setHeatmap(heatmap: boolean): void {
    this.overlay?.setSurfaceColors(heatmap ? this.measure.colors : null);
    this.viewport.invalidate();
  }

  setNetVisible(netVisible: boolean): void {
    this.overlay?.setNetVisible(netVisible);
    this.viewport.invalidate();
  }

  paint(points: NetPoints): void {
    points.paint(this.overlay);
    this.viewport.invalidate();
  }

  limitPoint(control: number): Vec3 {
    return this.surface?.limitPoint(control) ?? [0, 0, 0];
  }

  normalAt(control: number): Vec3 {
    return this.overlay?.normalAt(control) ?? [0, 0, 1];
  }
}
