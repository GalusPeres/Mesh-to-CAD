import * as THREE from 'three';
import { describe, expect, it } from 'vitest';

import { type FaceIdImage, decodeFaceId, encodeFaceId, faceIdAt } from './faceIds';
import { type PickView, isFaceVisible, projectToScreen } from './scanVisibility';
import { pickFacesInPolygon, rasterisePolygon } from './workers/polygonPick';

const SIZE = 100;

function viewOf(camera: THREE.Camera, clip: PickView['clip'] = null): PickView {
  camera.updateMatrixWorld();
  const toClip = new THREE.Matrix4().multiplyMatrices(
    camera.projectionMatrix,
    camera.matrixWorldInverse,
  );
  const perspective = camera instanceof THREE.PerspectiveCamera;
  return {
    toClip: toClip.elements,
    toView: camera.matrixWorldInverse.elements,
    orthographic: !perspective,
    width: SIZE,
    height: SIZE,
    pixelSize: perspective ? (2 * Math.tan(((camera.fov / 2) * Math.PI) / 180)) / SIZE : 100 / SIZE,
    clip,
  };
}

function orthographicView(clip: PickView['clip'] = null): PickView {
  // 1 CSS pixel = 1 mm, camera 100 mm above the XY plane looking down.
  const camera = new THREE.OrthographicCamera(-50, 50, 50, -50, 0.1, 1000);
  camera.position.set(0, 0, 100);
  camera.lookAt(0, 0, 0);
  return viewOf(camera, clip);
}

/** An id image that shows `face` at the pixel of screen point (x, y) and nothing else. */
function imageShowing(face: number, x: number, y: number): FaceIdImage {
  const ids = new Uint32Array(SIZE * SIZE);
  ids[(SIZE - 1 - Math.floor(y)) * SIZE + Math.floor(x)] = face + 1;
  return { ids, width: SIZE, height: SIZE, scale: 1 };
}

describe('face ids', () => {
  it('round-trip through the four bytes of a pixel', () => {
    for (const face of [0, 1, 255, 256, 65_535, 1_999_999, 16_777_300]) {
      const bytes = encodeFaceId(face);
      expect(bytes.every((byte) => byte >= 0 && byte <= 255)).toBe(true);
      expect(decodeFaceId(...bytes)).toBe(face);
      // Little-endian Uint32 view of the RGBA bytes gives id + 1 directly.
      expect(new Uint32Array(new Uint8Array(bytes).buffer)[0]).toBe(face + 1);
    }
    expect(decodeFaceId(0, 0, 0, 0)).toBe(-1);
  });

  it('are looked up with rows running bottom to top', () => {
    const image = imageShowing(7, 12.4, 3.9);
    expect(faceIdAt(image, 12.9, 3.1)).toBe(7);
    expect(faceIdAt(image, 12.4, 4.2)).toBe(-1);
    expect(faceIdAt(image, -1, 3)).toBe(-1);
    expect(faceIdAt({ ...image, scale: 2 }, 6.2, 1.9)).toBe(7);
  });
});

describe('visible-only picking', () => {
  // Face 0 is drawn; 1 is a sub-pixel neighbour on the same surface; 2 lies 10 mm
  // behind; 3 is the back of a 0.5 mm sheet; 4 sits on the outline.
  const centroids = new Float32Array([0, 0, 0, 0.3, 0, 0, 0, 0, -10, 0, 0, -0.5, 20, 20, 0]);
  const normals = new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, -1, 0, 0, 1]);

  it('projects scan points to CSS pixels', () => {
    const screen = { x: 0, y: 0 };
    expect(projectToScreen(orthographicView(), 10, 20, 0, screen)).toBe(true);
    expect(screen.x).toBeCloseTo(60);
    expect(screen.y).toBeCloseTo(30);
    expect(projectToScreen(orthographicView(), 0, 0, 500, screen)).toBe(false);
  });

  it.each([
    ['orthographic', orthographicView()],
    [
      'perspective',
      (() => {
        const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
        camera.position.set(0, 0, 100);
        camera.lookAt(0, 0, 0);
        return viewOf(camera);
      })(),
    ],
  ] as const)('keeps surface faces and rejects hidden ones (%s)', (_name, view) => {
    const at = { x: 0, y: 0 };
    projectToScreen(view, 0, 0, 0, at);
    const image = imageShowing(0, at.x, at.y);
    const visible = [0, 1, 2, 3].map((face) => {
      const screen = { x: 0, y: 0 };
      const o = face * 3;
      projectToScreen(view, centroids[o]!, centroids[o + 1]!, centroids[o + 2]!, screen);
      return isFaceVisible(face, screen.x, screen.y, centroids, normals, view, image);
    });
    expect(visible).toEqual([true, true, false, false]);
    const outline = { x: 0, y: 0 };
    projectToScreen(view, 20, 20, 0, outline);
    expect(isFaceVisible(4, outline.x, outline.y, centroids, normals, view, image)).toBe(true);
  });
});

describe('polygon picking', () => {
  // A 20 x 20 grid of faces with centroids at integer millimetres, all facing up.
  const count = 20 * 20;
  const centroids = new Float32Array(count * 3);
  const normals = new Float32Array(count * 3);
  for (let face = 0; face < count; face += 1) {
    centroids[face * 3] = (face % 20) - 10 + 0.25;
    centroids[face * 3 + 1] = Math.floor(face / 20) - 10 + 0.25;
    normals[face * 3 + 2] = 1;
  }
  // Screen square from (45, 45) to (55, 55) = world x, y in [-5, 5).
  const square = new Float32Array([45, 45, 55, 45, 55, 55, 45, 55]);
  const inSquare = (face: number) => {
    const x = centroids[face * 3]!;
    const y = centroids[face * 3 + 1]!;
    return x >= -5 && x < 5 && y > -5 && y <= 5;
  };

  it('rasterises polygons at pixel centres', () => {
    const mask = rasterisePolygon(new Float32Array([0, 0, 4, 0, 0, 4]), 100, 100);
    expect(mask).not.toBeNull();
    const rows = Array.from({ length: mask!.height }, (_, row) =>
      Array.from(mask!.mask.subarray(row * mask!.width, (row + 1) * mask!.width)).join(''),
    );
    expect(rows).toEqual(['1110', '1100', '1000', '0000']);
    expect(rasterisePolygon(new Float32Array([0, 0, 1, 1]), 100, 100)).toBeNull();
  });

  it('picks faces whose centroid lies inside the polygon', () => {
    const view = orthographicView();
    const faces = pickFacesInPolygon(
      { polygon: square, view, hidden: null, image: null },
      centroids,
      normals,
    );
    const expected = Array.from({ length: count }, (_, face) => face).filter(inSquare);
    expect(Array.from(faces)).toEqual(expected);
  });

  it('leaves out hidden faces and faces cut away by the section plane', () => {
    const hidden = new Uint8Array(count);
    const first = Array.from({ length: count }, (_, face) => face).find(inSquare)!;
    hidden[first] = 1;
    // Cut away x > 0.
    const view = orthographicView([1, 0, 0, 0]);
    const faces = Array.from(
      pickFacesInPolygon({ polygon: square, view, hidden, image: null }, centroids, normals),
    );
    expect(faces).not.toContain(first);
    expect(faces.length).toBeGreaterThan(0);
    expect(faces.every((face) => centroids[face * 3]! < 0)).toBe(true);
  });
});
