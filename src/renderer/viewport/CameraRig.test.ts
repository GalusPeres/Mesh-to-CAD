import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Vec3 } from './api';
import { orbitPose, viewQuaternion } from './cameraMath';
import { CameraRig } from './CameraRig';

function fakeElement(): HTMLElement {
  return {
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    getBoundingClientRect: () => ({ left: 0, top: 0 }),
  } as unknown as HTMLElement;
}

function rig(width = 800, height = 500): CameraRig {
  const camera = new CameraRig(new THREE.Scene(), fakeElement(), {
    pickPivot: () => null,
    invertWheel: () => false,
    onChange: () => undefined,
  });
  camera.resize(width, height);
  return camera;
}

const BOX: [Vec3, Vec3] = [
  [-20, 5, 0],
  [80, 45, 12],
];

function corners([min, max]: [Vec3, Vec3]): THREE.Vector3[] {
  return Array.from(
    { length: 8 },
    (_, i) =>
      new THREE.Vector3(i & 1 ? max[0] : min[0], i & 2 ? max[1] : min[1], i & 4 ? max[2] : min[2]),
  );
}

/** Largest |NDC| of the box corners: <= 1 means the box is fully visible. */
function extent(camera: THREE.Camera): number {
  camera.updateMatrixWorld();
  return Math.max(
    ...corners(BOX).flatMap((corner) => {
      const p = corner.project(camera);
      return [Math.abs(p.x), Math.abs(p.y), Math.abs(p.z)];
    }),
  );
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', () => 0);
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
  vi.stubGlobal('window', { matchMedia: () => ({ matches: true }) });
});

afterEach(() => vi.unstubAllGlobals());

describe('camera rig', () => {
  it.each(['orthographic', 'perspective'] as const)(
    'fits a box so that it is fully visible and fills the view (%s)',
    (projection) => {
      const camera = rig();
      camera.setProjection(projection);
      camera.setSceneBounds([30, 25, 6], 60);
      camera.setStandardView('iso');
      camera.fitBox(...BOX, false);
      const size = extent(camera.camera);
      expect(size).toBeLessThanOrEqual(1);
      // The bounding sphere touches the frame: the box itself fills at least half of it.
      expect(size).toBeGreaterThan(0.5);
      const target = new THREE.Vector3(...camera.target);
      expect(target.distanceTo(new THREE.Vector3(30, 25, 6))).toBeLessThan(1e-9);
    },
  );

  it.each([
    ['front', [0, 1, 0], [1, 0, 0]],
    ['back', [0, -1, 0], [-1, 0, 0]],
    ['left', [1, 0, 0], [0, -1, 0]],
    ['right', [-1, 0, 0], [0, 1, 0]],
    ['top', [0, 0, -1], [1, 0, 0]],
    ['bottom', [0, 0, 1], [1, 0, 0]],
  ] as const)('shows the %s view with the expected screen axes', (view, forward, right) => {
    const camera = rig();
    // With reduced motion the transition is instant.
    camera.setStandardView(view);
    const q = camera.camera.quaternion;
    const f = new THREE.Vector3(0, 0, -1).applyQuaternion(q);
    const r = new THREE.Vector3(1, 0, 0).applyQuaternion(q);
    expect(f.distanceTo(new THREE.Vector3(...forward))).toBeLessThan(1e-9);
    expect(r.distanceTo(new THREE.Vector3(...right))).toBeLessThan(1e-9);
  });

  it('keeps the visible height when switching the projection', () => {
    const camera = rig();
    camera.fitBox(...BOX, false);
    const before = camera.worldPerPixel(camera.target);
    camera.setProjection('perspective');
    expect(camera.worldPerPixel(camera.target)).toBeCloseTo(before, 9);
    camera.setProjection('orthographic');
    expect(camera.worldPerPixel(camera.target)).toBeCloseTo(before, 9);
  });

  it('zooms towards the point under the cursor', () => {
    const camera = rig();
    camera.fitBox(...BOX, false);
    const cursor = { x: 600, y: 120 };
    const ray = new THREE.Raycaster();
    ray.setFromCamera(camera.toNdc(cursor), camera.camera);
    const point = ray.ray.at(10, new THREE.Vector3());
    camera.zoomAt(cursor, 0.5);
    const screen = camera.toScreen([point.x, point.y, point.z]);
    expect(screen?.x).toBeCloseTo(cursor.x, 6);
    expect(screen?.y).toBeCloseTo(cursor.y, 6);
  });
});

describe('orbiting', () => {
  it('keeps the pivot on the same screen position', () => {
    const quaternion = viewQuaternion([-1, 1, -1], [0, 0, 1]);
    const pose = {
      position: new THREE.Vector3(100, -100, 100),
      quaternion,
      target: new THREE.Vector3(0, 0, 0),
      halfHeight: 50,
    };
    const pivot = new THREE.Vector3(12, -3, 8);
    const toCamera = (p: THREE.Vector3) =>
      p.clone().sub(pose.position).applyQuaternion(pose.quaternion.clone().invert());
    const before = toCamera(pivot);
    orbitPose(pose, pivot, 0.4, -0.25);
    const after = toCamera(pivot);
    expect(after.distanceTo(before)).toBeLessThan(1e-9);
    // Yaw turns about world Z: the camera keeps its height relation to the pivot only
    // through pitch, and screen right stays horizontal.
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(pose.quaternion);
    expect(Math.abs(right.z)).toBeLessThan(1e-9);
  });
});
