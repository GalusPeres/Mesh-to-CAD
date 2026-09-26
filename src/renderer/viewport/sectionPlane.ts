// The section plane (viewStore.sectionPlane): one clipping plane shared by the
// scan and body materials, the scan's section outline computed from the drawn
// triangles, and the gizmo (plane handle plus two rotation arcs).

import * as THREE from 'three';
import { INTERSECTED, NOT_INTERSECTED } from 'three-mesh-bvh';

import type { SectionPlane } from '../state/viewStore';
import type { Vec3 } from './api';
import type { DepthBias } from './depthBias';
import { createLines } from './displayItems';
import { perpendicular, rotateAround } from './handleMath';
import type { InternalHandleFactory } from './handles';
import { SCENE_COLORS } from './palette';
import type { ScanMesh } from './scanMesh';
import { faceSection, sectionSegments } from './sectionOutline';

const OUTLINE_PX = 1.5;
const OUTLINE_BIAS = 2;
/** A plane so far away that nothing is ever clipped; keeps the shader variant fixed. */
const FAR = 1e20;

const vector = (value: readonly number[]) => new THREE.Vector3(value[0], value[1], value[2]);
const tuple = (value: THREE.Vector3): Vec3 => [value.x, value.y, value.z];

/** Segments of the outline in scan-local coordinates, using the BVH when available. */
export function scanOutline(scan: ScanMesh, localPlane: THREE.Plane): Float32Array {
  const normal: [number, number, number] = [
    localPlane.normal.x,
    localPlane.normal.y,
    localPlane.normal.z,
  ];
  const offset = -localPlane.constant;
  const bvh = scan.topology?.bvh;
  if (!bvh) return sectionSegments(scan.positions, normal, offset, (face) => scan.isHidden(face));
  const out: number[] = [];
  bvh.shapecast({
    intersectsBounds: (box) => (box.intersectsPlane(localPlane) ? INTERSECTED : NOT_INTERSECTED),
    intersectsRange: (start, count) => {
      for (let i = start; i < start + count; i += 1) {
        const face = bvh.resolveTriangleIndex(i);
        if (!scan.isHidden(face)) faceSection(scan.positions, face, normal, offset, out);
      }
      return false;
    },
  });
  return Float32Array.from(out);
}

export interface SectionHost {
  readonly handles: InternalHandleFactory;
  readonly bias: DepthBias;
  /** Parent of the outline; carries the scan transform. */
  readonly scanGroup: THREE.Group;
  scan(): ScanMesh | null;
  /** Size of the drawn scene, for the gizmo. */
  sceneRadius(): number;
  /** Write the plane to the view store. */
  commit(plane: SectionPlane | null): void;
  invalidate(): void;
}

export class SectionPlaneController {
  /** Clipping plane in three.js convention (the side the normal points to is kept). */
  readonly clippingPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), FAR);
  private current: SectionPlane | null = null;
  private outline: { object: THREE.Object3D; dispose(): void } | null = null;
  private outlineDirty = false;
  private gizmo: { dispose(): void }[] = [];
  private dragging = false;

  constructor(private readonly host: SectionHost) {}

  get plane(): SectionPlane | null {
    return this.current;
  }

  set(plane: SectionPlane | null): void {
    this.current = plane;
    if (plane) {
      const normal = vector(plane.normal).normalize();
      // Cut away the side the section normal points to.
      this.clippingPlane.setFromNormalAndCoplanarPoint(normal.negate(), vector(plane.origin));
    } else {
      this.clippingPlane.set(new THREE.Vector3(0, 0, 1), FAR);
    }
    this.outlineDirty = true;
    if (!this.dragging) this.buildGizmo();
    this.host.invalidate();
  }

  /** The scan or its hidden faces changed. */
  scanChanged(): void {
    this.outlineDirty = true;
  }

  /** Recompute the outline if needed; called once per frame before rendering. */
  update(): void {
    if (!this.outlineDirty) return;
    this.outlineDirty = false;
    this.outline?.dispose();
    this.outline = null;
    const scan = this.host.scan();
    if (!this.current || !scan) return;
    const toLocal = this.host.scanGroup.matrix.clone().invert();
    const localPlane = this.clippingPlane.clone().applyMatrix4(toLocal).negate();
    const segments = scanOutline(scan, localPlane);
    if (segments.length === 0) return;
    const { object, material } = createLines(
      segments,
      OUTLINE_PX,
      SCENE_COLORS.section,
      this.host.bias,
      OUTLINE_BIAS,
    );
    this.host.scanGroup.add(object);
    this.outline = {
      object,
      dispose: () => {
        this.host.scanGroup.remove(object);
        (object as THREE.Mesh).geometry.dispose();
        material.dispose();
      },
    };
  }

  /** Part-coordinate plane through `center` whose normal is the world axis facing the viewer. */
  static facingViewer(center: Vec3, towardsCamera: THREE.Vector3): SectionPlane {
    const axes: Vec3[] = [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ];
    let best: Vec3 = [0, 0, 1];
    let bestDot = 0;
    for (const axis of axes) {
      const d = towardsCamera.dot(vector(axis));
      if (Math.abs(d) > Math.abs(bestDot)) {
        bestDot = d;
        best = axis;
      }
    }
    const sign = bestDot < 0 ? -1 : 1;
    return { origin: center, normal: [best[0] * sign, best[1] * sign, best[2] * sign] };
  }

  dispose(): void {
    this.clearGizmo();
    this.outline?.dispose();
  }

  private clearGizmo(): void {
    this.gizmo.forEach((handle) => handle.dispose());
    this.gizmo = [];
  }

  private buildGizmo(): void {
    this.clearGizmo();
    const plane = this.current;
    if (!plane) return;
    const origin = vector(plane.origin);
    const normal = vector(plane.normal).normalize();
    const u = vector(perpendicular(tuple(normal)));
    const v = normal.clone().cross(u);
    const size = Math.max(this.host.sceneRadius() * 1.2, 1);
    const moving = (next: SectionPlane) => {
      this.dragging = true;
      this.host.commit(next);
    };
    const done = (next: SectionPlane) => {
      this.dragging = false;
      this.host.commit(next);
    };
    const look = {
      color: (colors: { accent: string }) => colors.accent,
      lineWidth: 1,
      onCancel: () => done(plane),
    };
    const shifted = (offset: number): SectionPlane => ({
      origin: tuple(origin.clone().addScaledVector(normal, offset)),
      normal: tuple(normal),
    });
    const turned = (axis: THREE.Vector3, degrees: number): SectionPlane => ({
      origin: tuple(origin),
      normal: rotateAround(tuple(normal), tuple(axis), degrees),
    });
    this.gizmo.push(
      this.host.handles.plane(
        {
          origin: tuple(origin),
          normal: tuple(normal),
          xDirection: tuple(u),
          size,
          value: 0,
          onChange: (value) => moving(shifted(value as number)),
          onCommit: (value) => done(shifted(value as number)),
        },
        look,
      ),
    );
    // Turning about u tilts the normal towards v and back; the knob starts on v.
    for (const [axis, reference] of [
      [u, v],
      [v, u.clone().negate()],
    ] as const) {
      this.gizmo.push(
        this.host.handles.arc(
          {
            center: tuple(origin),
            axis: tuple(axis),
            reference: tuple(reference),
            radius: size / 2,
            value: 0,
            onChange: (value) => moving(turned(axis, value as number)),
            onCommit: (value) => done(turned(axis, value as number)),
          },
          look,
        ),
      );
    }
  }
}
