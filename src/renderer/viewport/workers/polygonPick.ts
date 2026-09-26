// Lasso and rectangle picking: faces whose centroid projects inside a screen
// polygon. The polygon is rasterised once into a pixel mask, so each face costs
// one projection and one lookup however many corners the lasso has.

import type { FaceIdImage } from '../faceIds';
import {
  type PickView,
  type ScreenPosition,
  isClipped,
  isFaceVisible,
  projectToScreen,
} from '../scanVisibility';

export interface PolygonPickQuery {
  /** Polygon corners as x, y pairs in CSS pixels. */
  polygon: Float32Array;
  view: PickView;
  /** One byte per face, 1 = hidden. */
  hidden: Uint8Array | null;
  /** Face-id image of the current view; null picks through the part. */
  image: FaceIdImage | null;
}

export interface PolygonMask {
  mask: Uint8Array;
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Even-odd fill of a polygon, sampled at pixel centres and clipped to the viewport. */
export function rasterisePolygon(
  polygon: Float32Array,
  viewportWidth: number,
  viewportHeight: number,
): PolygonMask | null {
  const count = polygon.length / 2;
  if (count < 3) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < count; i += 1) {
    const x = polygon[i * 2] ?? 0;
    const y = polygon[i * 2 + 1] ?? 0;
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  const left = Math.max(0, Math.floor(minX));
  const top = Math.max(0, Math.floor(minY));
  const right = Math.min(Math.ceil(viewportWidth), Math.ceil(maxX));
  const bottom = Math.min(Math.ceil(viewportHeight), Math.ceil(maxY));
  const width = right - left;
  const height = bottom - top;
  if (width <= 0 || height <= 0) return null;
  const mask = new Uint8Array(width * height);
  const crossings: number[] = [];
  for (let row = 0; row < height; row += 1) {
    const y = top + row + 0.5;
    crossings.length = 0;
    for (let i = 0, j = count - 1; i < count; j = i, i += 1) {
      const xi = polygon[i * 2] ?? 0;
      const yi = polygon[i * 2 + 1] ?? 0;
      const xj = polygon[j * 2] ?? 0;
      const yj = polygon[j * 2 + 1] ?? 0;
      if (yi > y !== yj > y) crossings.push(xi + ((y - yi) * (xj - xi)) / (yj - yi));
    }
    crossings.sort((a, b) => a - b);
    for (let k = 0; k + 1 < crossings.length; k += 2) {
      // Pixel centres x + 0.5 inside [from, to).
      const from = Math.max(0, Math.ceil((crossings[k] ?? 0) - 0.5) - left);
      const to = Math.min(width, Math.ceil((crossings[k + 1] ?? 0) - 0.5) - left);
      if (to > from) mask.fill(1, row * width + from, row * width + to);
    }
  }
  return { mask, left, top, width, height };
}

export function insideMask(mask: PolygonMask, x: number, y: number): boolean {
  const column = Math.floor(x) - mask.left;
  const row = Math.floor(y) - mask.top;
  if (column < 0 || row < 0 || column >= mask.width || row >= mask.height) return false;
  return mask.mask[row * mask.width + column] === 1;
}

export function pickFacesInPolygon(
  query: PolygonPickQuery,
  centroids: Float32Array,
  faceNormals: Float32Array,
): Uint32Array {
  const { view, hidden, image } = query;
  const mask = rasterisePolygon(query.polygon, view.width, view.height);
  if (!mask) return new Uint32Array();
  const faceCount = centroids.length / 3;
  const picked = new Uint32Array(faceCount);
  let count = 0;
  const screen: ScreenPosition = { x: 0, y: 0 };
  for (let face = 0; face < faceCount; face += 1) {
    if (hidden && hidden[face]) continue;
    const o = face * 3;
    const inView = projectToScreen(
      view,
      centroids[o] ?? 0,
      centroids[o + 1] ?? 0,
      centroids[o + 2] ?? 0,
      screen,
    );
    if (!inView || !insideMask(mask, screen.x, screen.y)) continue;
    if (isClipped(view, centroids, face)) continue;
    if (image && !isFaceVisible(face, screen.x, screen.y, centroids, faceNormals, view, image))
      continue;
    picked[count] = face;
    count += 1;
  }
  return picked.slice(0, count);
}
