// The net's deviation from the scan: signed distances of the dense limit-surface
// vertices, their heatmap colours and the summary the panel shows. A drag measures
// only the rows it moved; a changed net is measured a chunk per animation frame.

import type { Viewport } from '../../viewport/api';
import {
  type DeviationSummary,
  type HeatmapScale,
  SEARCH_FACTOR,
  colorize,
  deviationSummary,
  heatmapScale,
} from './heatmap';
import type { LimitSurface } from './limitSurface';

/** Dense vertices measured per animation frame after a change of the whole net. */
const MEASURE_CHUNK = 6000;

const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

export class NetMeasure {
  /** RGB per dense vertex. */
  colors = new Float32Array(0);
  private distances = new Float32Array(0);
  private scale: HeatmapScale;
  private token = 0;

  constructor(
    private readonly viewport: Viewport,
    tolerance: number,
  ) {
    this.scale = heatmapScale(tolerance);
  }

  get tolerance(): number {
    return this.scale.tolerance;
  }

  /** Change the colour scale; false if it stays the same. */
  setTolerance(tolerance: number): boolean {
    if (tolerance === this.scale.tolerance) return false;
    this.scale = heatmapScale(tolerance);
    return true;
  }

  /** Start over for a new dense surface: nothing measured yet. */
  reset(surface: LimitSurface): void {
    this.cancel();
    this.distances = new Float32Array(surface.fineCount).fill(Number.NaN);
    this.colors = new Float32Array(surface.fineCount * 3);
  }

  /** Measure some dense rows now (during a drag); false while the scan cannot be searched. */
  rows(surface: LimitSurface, rows: Uint32Array): boolean {
    const measured = this.viewport.scanSurface.distances(
      surface.positions,
      this.distances,
      this.scale.range * SEARCH_FACTOR,
      rows,
    );
    if (measured) colorize(this.distances, this.scale, this.colors, rows);
    return measured;
  }

  /**
   * Measure every dense vertex, a chunk per frame, calling `onChunk` after each. Resolves
   * with the summary, or null when a newer measurement took over.
   */
  async all(surface: LimitSurface, onChunk: () => void): Promise<DeviationSummary | null> {
    const token = ++this.token;
    await this.viewport.scanTopology().catch(() => undefined);
    for (let start = 0; start < surface.fineCount; start += MEASURE_CHUNK) {
      if (token !== this.token) return null;
      const end = Math.min(surface.fineCount, start + MEASURE_CHUNK);
      if (
        !this.rows(
          surface,
          Uint32Array.from({ length: end - start }, (_, i) => start + i),
        )
      )
        return null;
      onChunk();
      await nextFrame();
    }
    return token === this.token ? this.summary() : null;
  }

  /** Stop a running `all`. */
  cancel(): void {
    this.token += 1;
  }

  summary(): DeviationSummary {
    return deviationSummary(this.distances, this.scale.tolerance);
  }
}
