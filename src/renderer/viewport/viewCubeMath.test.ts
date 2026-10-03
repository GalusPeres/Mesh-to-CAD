import { describe, expect, it } from 'vitest';

import type { Vec3 } from './api';
import { STANDARD_VIEWS, cameraPosition } from './cameraMath';
import { CUBE_FACES, CUBE_ZONES, cubePieces, cubeZone, faceRight, zoneView } from './viewCubeMath';

const key = (zone: Vec3) => zone.join(',');
const norm = (v: readonly number[]) => Math.hypot(...v);
const dot = (a: readonly number[], b: readonly number[]) =>
  a.reduce((sum, value, index) => sum + value * (b[index] ?? 0), 0);

describe('view cube zones', () => {
  it('are 26 distinct directions: 6 faces, 12 edges, 8 corners', () => {
    expect(new Set(CUBE_ZONES.map(key)).size).toBe(26);
    const byAxes = [1, 2, 3].map(
      (count) => CUBE_ZONES.filter((zone) => zone.filter((v) => v !== 0).length === count).length,
    );
    expect(byAxes).toEqual([6, 12, 8]);
  });

  it('cover the cube with 54 pieces: 1 per face zone, 2 per edge, 3 per corner', () => {
    const pieces = cubePieces();
    expect(pieces).toHaveLength(54);
    const counts = new Map<string, number>();
    for (const piece of pieces) counts.set(key(piece.zone), (counts.get(key(piece.zone)) ?? 0) + 1);
    expect(counts.size).toBe(26);
    for (const zone of CUBE_ZONES) {
      const axes = zone.filter((v) => v !== 0).length;
      expect(counts.get(key(zone)), key(zone)).toBe(axes);
    }
    // Every piece lies on its face and belongs to a zone containing that face.
    for (const piece of pieces) {
      expect(dot(piece.center, piece.face.normal)).toBeCloseTo(1);
      expect(dot(piece.zone, piece.face.normal)).toBe(1);
    }
  });

  it('classify points on the surface', () => {
    expect(cubeZone([0.1, -1, 0.3])).toEqual([0, -1, 0]);
    expect(cubeZone([0.9, -1, 0])).toEqual([1, -1, 0]);
    expect(cubeZone([0.9, -1, -0.95])).toEqual([1, -1, -1]);
    expect(cubeZone([0, 0, 1])).toEqual([0, 0, 1]);
  });

  it('look from the zone towards the centre with an upright camera', () => {
    for (const zone of CUBE_ZONES) {
      const { direction, up } = zoneView(zone);
      expect(norm(direction)).toBeCloseTo(1);
      expect(dot(direction, zone)).toBeCloseTo(-norm(zone));
      expect(Math.abs(dot(direction, up))).toBeLessThan(0.99);
    }
  });

  it('turn face zones into the standard views', () => {
    const views = {
      front: [0, -1, 0],
      back: [0, 1, 0],
      left: [-1, 0, 0],
      right: [1, 0, 0],
    } as const;
    for (const [name, zone] of Object.entries(views)) {
      const expected = STANDARD_VIEWS[name as keyof typeof views].direction;
      zoneView(zone).direction.forEach((value, axis) =>
        expect(value, name).toBeCloseTo(expected[axis] ?? Number.NaN),
      );
    }
    expect(zoneView([0, 0, 1])).toBe(STANDARD_VIEWS.top);
    expect(zoneView([0, 0, -1])).toBe(STANDARD_VIEWS.bottom);
    // The front-right-top corner is the isometric view.
    const corner = zoneView([1, -1, 1]).direction;
    STANDARD_VIEWS.iso.direction.forEach((value, axis) => expect(corner[axis]).toBeCloseTo(value));
  });

  it('put each face label where the camera of that view sees it upright', () => {
    for (const face of CUBE_FACES) {
      const view = zoneView(face.normal);
      const camera = cameraPosition([0, 0, 0], view.direction, 5);
      // The camera sits outside the labelled face.
      expect(dot(camera, face.normal)).toBeGreaterThan(0);
      // Screen right = direction x up must equal the label's right direction.
      const [d, u] = [view.direction, view.up];
      const screenRight = [
        d[1] * u[2] - d[2] * u[1],
        d[2] * u[0] - d[0] * u[2],
        d[0] * u[1] - d[1] * u[0],
      ];
      expect(screenRight.map((v) => v + 0)).toEqual(faceRight(face).map((v) => v + 0));
    }
  });
});
