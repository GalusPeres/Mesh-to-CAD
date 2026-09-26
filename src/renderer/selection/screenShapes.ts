// Screen-space geometry of the selection gestures, in CSS pixels relative to the
// viewport canvas.

import type { ScreenPoint } from '../viewport/api';

/** Even-odd test of a point against a closed polygon of x, y pairs. */
export function pointInPolygon(point: ScreenPoint, polygon: ArrayLike<number>): boolean {
  let inside = false;
  const count = polygon.length / 2;
  for (let i = 0, j = count - 1; i < count; j = i, i += 1) {
    const xi = polygon[i * 2] ?? 0;
    const yi = polygon[i * 2 + 1] ?? 0;
    const xj = polygon[j * 2] ?? 0;
    const yj = polygon[j * 2 + 1] ?? 0;
    const crosses = yi > point.y !== yj > point.y;
    if (crosses && point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The rectangle spanned by two corners as a polygon (x, y pairs, clockwise on screen). */
export function rectanglePolygon(a: ScreenPoint, b: ScreenPoint): Float32Array {
  const left = Math.min(a.x, b.x);
  const right = Math.max(a.x, b.x);
  const top = Math.min(a.y, b.y);
  const bottom = Math.max(a.y, b.y);
  return Float32Array.from([left, top, right, top, right, bottom, left, bottom]);
}

/** Area of a polygon of x, y pairs (shoelace formula, absolute value). */
export function polygonArea(polygon: ArrayLike<number>): number {
  let twice = 0;
  const count = polygon.length / 2;
  for (let i = 0, j = count - 1; i < count; j = i, i += 1) {
    twice +=
      (polygon[j * 2] ?? 0) * (polygon[i * 2 + 1] ?? 0) -
      (polygon[i * 2] ?? 0) * (polygon[j * 2 + 1] ?? 0);
  }
  return Math.abs(twice) / 2;
}

/**
 * Points along the segment from `from` (exclusive) to `to` (inclusive), at most
 * `spacing` apart, so a fast brush stroke leaves no gaps.
 */
export function strokeSamples(from: ScreenPoint, to: ScreenPoint, spacing: number): ScreenPoint[] {
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  const steps = Math.max(1, Math.ceil(length / Math.max(spacing, 1)));
  const samples: ScreenPoint[] = [];
  for (let step = 1; step <= steps; step += 1) {
    const t = step / steps;
    samples.push({ x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t });
  }
  return samples;
}

/** Collects a lasso path, dropping points closer than `minSpacing` to the previous one. */
export class LassoPath {
  private readonly points: number[] = [];

  constructor(private readonly minSpacing = 3) {}

  add(point: ScreenPoint): boolean {
    const count = this.points.length;
    if (count >= 2) {
      const dx = point.x - (this.points[count - 2] ?? 0);
      const dy = point.y - (this.points[count - 1] ?? 0);
      if (dx * dx + dy * dy < this.minSpacing * this.minSpacing) return false;
    }
    this.points.push(point.x, point.y);
    return true;
  }

  get pointCount(): number {
    return this.points.length / 2;
  }

  polygon(): Float32Array {
    return Float32Array.from(this.points);
  }
}
