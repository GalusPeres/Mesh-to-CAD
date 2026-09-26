// Screen projection and visibility of scan faces for brush and lasso picking.
// Shared by the UI thread (brush) and the polygon-picking worker (lasso), so it
// works on plain arrays only.
//
// A face counts as visible when the face-id image shows it at its centroid, or,
// for faces smaller than a pixel that lost the pixel to a neighbour, when its
// centroid lies no deeper than the surface drawn at that pixel (plus two pixels)
// and both face the camera the same way. Faces behind a wall are far deeper;
// the back of a thin sheet faces away.

import { type FaceIdImage, faceIdAt } from './faceIds';

/** The camera and scan placement as plain numbers (column-major 4 x 4 matrices). */
export interface PickView {
  /** Scan-local coordinates to clip space. */
  toClip: ArrayLike<number>;
  /** Scan-local coordinates to view space (rigid scan transform). */
  toView: ArrayLike<number>;
  orthographic: boolean;
  /** Viewport size in CSS pixels. */
  width: number;
  height: number;
  /** World size of a CSS pixel: everywhere (orthographic) or per unit of distance (perspective). */
  pixelSize: number;
  /** Section plane in scan-local coordinates; a face with n . centroid > d is cut away. */
  clip: readonly [number, number, number, number] | null;
}

export interface ScreenPosition {
  x: number;
  y: number;
}

/** Depth tolerance of the sub-pixel test in pixels. */
const DEPTH_TOLERANCE_PX = 2;
/** Below this cosine between the view ray and a face, its plane gives no usable depth. */
const GRAZING = 0.1;

const m = (matrix: ArrayLike<number>, index: number) => matrix[index] ?? 0;

/** Screen position of a scan-local point; false behind the camera or outside the depth range. */
export function projectToScreen(
  view: PickView,
  x: number,
  y: number,
  z: number,
  out: ScreenPosition,
): boolean {
  const c = view.toClip;
  const w = m(c, 3) * x + m(c, 7) * y + m(c, 11) * z + m(c, 15);
  if (w <= 0) return false;
  const cx = (m(c, 0) * x + m(c, 4) * y + m(c, 8) * z + m(c, 12)) / w;
  const cy = (m(c, 1) * x + m(c, 5) * y + m(c, 9) * z + m(c, 13)) / w;
  const cz = (m(c, 2) * x + m(c, 6) * y + m(c, 10) * z + m(c, 14)) / w;
  if (cz < -1 || cz > 1) return false;
  out.x = ((cx + 1) / 2) * view.width;
  out.y = ((1 - cy) / 2) * view.height;
  return true;
}

export function isClipped(view: PickView, centroids: Float32Array, face: number): boolean {
  const plane = view.clip;
  if (!plane) return false;
  const o = face * 3;
  const side =
    plane[0] * (centroids[o] ?? 0) +
    plane[1] * (centroids[o + 1] ?? 0) +
    plane[2] * (centroids[o + 2] ?? 0);
  return side > plane[3];
}

interface ViewFace {
  px: number;
  py: number;
  pz: number;
  nx: number;
  ny: number;
  nz: number;
}

function toViewSpace(
  view: PickView,
  centroids: Float32Array,
  normals: Float32Array,
  face: number,
  out: ViewFace,
): void {
  const t = view.toView;
  const o = face * 3;
  const x = centroids[o] ?? 0;
  const y = centroids[o + 1] ?? 0;
  const z = centroids[o + 2] ?? 0;
  out.px = m(t, 0) * x + m(t, 4) * y + m(t, 8) * z + m(t, 12);
  out.py = m(t, 1) * x + m(t, 5) * y + m(t, 9) * z + m(t, 13);
  out.pz = m(t, 2) * x + m(t, 6) * y + m(t, 10) * z + m(t, 14);
  const a = normals[o] ?? 0;
  const b = normals[o + 1] ?? 0;
  const c = normals[o + 2] ?? 0;
  const nx = m(t, 0) * a + m(t, 4) * b + m(t, 8) * c;
  const ny = m(t, 1) * a + m(t, 5) * b + m(t, 9) * c;
  const nz = m(t, 2) * a + m(t, 6) * b + m(t, 10) * c;
  const length = Math.hypot(nx, ny, nz) || 1;
  out.nx = nx / length;
  out.ny = ny / length;
  out.nz = nz / length;
}

const candidate: ViewFace = { px: 0, py: 0, pz: 0, nx: 0, ny: 0, nz: 0 };
const drawn: ViewFace = { px: 0, py: 0, pz: 0, nx: 0, ny: 0, nz: 0 };

function facesCamera(view: PickView, face: ViewFace): boolean {
  return view.orthographic
    ? face.nz > 0
    : face.nx * face.px + face.ny * face.py + face.nz * face.pz < 0;
}

/**
 * Whether `face`, whose centroid projects to (x, y), is visible in the face-id
 * image. Hidden and clipped faces must be filtered before.
 */
export function isFaceVisible(
  face: number,
  x: number,
  y: number,
  centroids: Float32Array,
  normals: Float32Array,
  view: PickView,
  image: FaceIdImage,
): boolean {
  const shown = faceIdAt(image, x, y);
  if (shown === face) return true;
  // Background under the centroid: the face sits on the outline, nothing covers it.
  if (shown < 0) return true;
  toViewSpace(view, centroids, normals, face, candidate);
  toViewSpace(view, centroids, normals, shown, drawn);
  if (facesCamera(view, candidate) !== facesCamera(view, drawn)) return false;
  const gap = Math.hypot(candidate.px - drawn.px, candidate.py - drawn.py, candidate.pz - drawn.pz);
  let depth: number;
  let surface: number;
  let slack = 0;
  if (view.orthographic) {
    depth = -candidate.pz;
    if (Math.abs(drawn.nz) > GRAZING) {
      const planeZ =
        drawn.pz -
        (drawn.nx * (candidate.px - drawn.px) + drawn.ny * (candidate.py - drawn.py)) / drawn.nz;
      surface = -planeZ;
    } else {
      surface = -drawn.pz;
      slack = gap;
    }
  } else {
    depth = Math.hypot(candidate.px, candidate.py, candidate.pz);
    const along = drawn.nx * candidate.px + drawn.ny * candidate.py + drawn.nz * candidate.pz;
    if (Math.abs(along) > GRAZING * depth) {
      const t = (drawn.nx * drawn.px + drawn.ny * drawn.py + drawn.nz * drawn.pz) / along;
      surface = t * depth;
    } else {
      surface = Math.hypot(drawn.px, drawn.py, drawn.pz);
      slack = gap;
    }
  }
  const pixel = view.orthographic ? view.pixelSize : view.pixelSize * depth;
  return depth <= surface + slack + DEPTH_TOLERANCE_PX * pixel;
}
