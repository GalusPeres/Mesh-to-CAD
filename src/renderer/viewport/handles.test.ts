import * as THREE from 'three';
import { describe, expect, it } from 'vitest';

import type { Ray, ScreenPoint, Vec3, ViewportInteraction, ViewportPointerEvent } from './api';
import { createDepthBias } from './depthBias';
import {
  angleAround,
  closestAlongAxis,
  distanceToSegment,
  intersectPlane,
  perpendicular,
  rotateAround,
  wrapDegrees,
} from './handleMath';
import { type HandleHost, createHandleFactory } from './handles';

describe('handle drag maths', () => {
  it('finds the axis parameter closest to a ray', () => {
    const t = closestAlongAxis([0, 0, 0], [0, 0, 1], { origin: [10, 0, 5], direction: [-1, 0, 0] });
    expect(t).toBeCloseTo(5);
    expect(
      closestAlongAxis([0, 0, 0], [0, 0, 2], { origin: [1, 1, 1], direction: [0, 0, -1] }),
    ).toBeNaN();
  });

  it('intersects a ray with a plane', () => {
    const hit = intersectPlane({ origin: [1, 2, 10], direction: [0, 0, -1] }, [0, 0, 3], [0, 0, 1]);
    expect(hit).toEqual([1, 2, 3]);
    expect(
      intersectPlane({ origin: [0, 0, 1], direction: [1, 0, 0] }, [0, 0, 0], [0, 0, 1]),
    ).toBeNull();
  });

  it('measures angles around an axis from the reference direction', () => {
    expect(angleAround([0, 5, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeCloseTo(90);
    expect(angleAround([-5, 0, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeCloseTo(180);
    expect(angleAround([0, -5, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeCloseTo(-90);
  });

  it('wraps angle steps and rotates directions', () => {
    expect(wrapDegrees(190)).toBe(-170);
    expect(wrapDegrees(-190)).toBe(170);
    expect(wrapDegrees(-180)).toBe(180);
    expect(wrapDegrees(540)).toBe(180);
    const rotated = rotateAround([1, 0, 0], [0, 0, 1], 90);
    expect(rotated[0]).toBeCloseTo(0);
    expect(rotated[1]).toBeCloseTo(1);
  });

  it('finds perpendiculars and distances to screen segments', () => {
    for (const normal of [
      [0, 0, 1],
      [1, 0, 0],
      [0.3, -0.2, 0.9],
    ] as Vec3[]) {
      const p = perpendicular(normal);
      expect(Math.hypot(...p)).toBeCloseTo(1);
      expect(p[0] * normal[0] + p[1] * normal[1] + p[2] * normal[2]).toBeCloseTo(0);
    }
    expect(distanceToSegment({ x: 5, y: 3 }, { x: 0, y: 0 }, { x: 10, y: 0 })).toBeCloseTo(3);
    expect(distanceToSegment({ x: 13, y: 4 }, { x: 0, y: 0 }, { x: 10, y: 0 })).toBeCloseTo(5);
  });
});

/**
 * A 200 x 200 px view looking down the Z axis at the origin, 1 px = 1 mm, so
 * world (x, y) is at screen (100 + x, 100 - y).
 */
function testHost() {
  const interactions: ViewportInteraction[] = [];
  const frameHooks = new Set<() => void>();
  const host: HandleHost = {
    group: new THREE.Group(),
    bias: createDepthBias(),
    addInteraction: (interaction) => {
      interactions.push(interaction);
      return () => interactions.splice(interactions.indexOf(interaction), 1);
    },
    screenToRay: (at: ScreenPoint): Ray => ({
      origin: [at.x - 100, 100 - at.y, 500],
      direction: [0, 0, -1],
    }),
    worldToScreen: (point: Vec3) => ({ x: 100 + point[0], y: 100 - point[1] }),
    worldPerPixel: () => 1,
    colors: () => ({ neutral: '#e4e5e7', outline: '#1c1d20', accent: '#2b6bd0' }),
    beforeFrame: (update) => {
      frameHooks.add(update);
      return () => frameHooks.delete(update);
    },
    invalidate: () => undefined,
  };
  const event = (x: number, y: number, button = 0): ViewportPointerEvent => ({
    screen: { x, y },
    button,
    buttons: button === 0 ? 1 : 0,
    ctrl: false,
    shift: false,
    alt: false,
  });
  // Like the pointer router: the last added interaction is asked first.
  const down = (x: number, y: number, button = 0) =>
    [...interactions].reverse().find((i) => i.onPointerDown?.(event(x, y, button)));
  return { host, interactions, frameHooks, event, down };
}

describe('handles', () => {
  it('drag an arrow along its axis from where it was grabbed', () => {
    const { host, event, down } = testHost();
    const changes: number[] = [];
    let committed: unknown = null;
    const handle = createHandleFactory(host).arrow({
      origin: [0, 0, 0],
      direction: [1, 0, 0],
      value: 10,
      onChange: (value) => changes.push(value as number),
      onCommit: (value) => (committed = value),
    });
    expect(down(150, 100)).toBeUndefined();
    expect(down(100, 100, 2)).toBeUndefined();
    // Grabbed 3 px off the knob: the value keeps that offset.
    const owner = down(113, 100);
    expect(owner).toBeDefined();
    owner?.onPointerMove?.(event(133, 140));
    expect(changes.at(-1)).toBeCloseTo(30);
    owner?.onPointerUp?.(event(133, 140));
    expect(committed).toBeCloseTo(30);
    handle.dispose();
    expect(host.group.children).toHaveLength(0);
  });

  it('restore the value when Esc is pressed during a drag', () => {
    const { host, event, down } = testHost();
    const changes: number[] = [];
    createHandleFactory(host).plane({
      origin: [0, 0, 0],
      normal: [1, 0, 0],
      xDirection: [0, 1, 0],
      size: 40,
      value: 0,
      onChange: (value) => changes.push(value as number),
    });
    // Grab the rectangle edge, which is seen edge-on as a vertical line at x = 100.
    const owner = down(101, 90);
    owner?.onPointerMove?.(event(121, 90));
    expect(changes.at(-1)).toBeCloseTo(20);
    const escape = { key: 'Escape' } as KeyboardEvent;
    expect(owner?.onKeyDown?.(escape)).toBe(true);
    expect(changes.at(-1)).toBe(0);
  });

  it('turn an arc past 180 degrees without jumping', () => {
    const { host, event, down } = testHost();
    const changes: number[] = [];
    createHandleFactory(host).arc({
      center: [0, 0, 0],
      axis: [0, 0, 1],
      reference: [1, 0, 0],
      radius: 20,
      value: 0,
      onChange: (value) => changes.push(value as number),
    });
    const owner = down(120, 100);
    for (const [x, y] of [
      [100, 80],
      [80, 100],
      [100, 120],
    ] as const)
      owner?.onPointerMove?.(event(x, y));
    expect(changes.map((value) => Math.round(value))).toEqual([90, 180, 270]);
  });

  it('move a point in its plane and keep its on-screen size', () => {
    const { host, event, down, frameHooks } = testHost();
    let moved: unknown = null;
    createHandleFactory(host).point({
      position: [0, 0, 0],
      planeNormal: [0, 0, 1],
      onChange: (value) => (moved = value),
    });
    const owner = down(100, 100);
    owner?.onPointerMove?.(event(110, 90));
    expect(moved).toEqual([10, 10, 0]);
    expect(frameHooks.size).toBe(1);
  });
});
