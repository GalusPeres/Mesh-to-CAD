// pick(): what lies under the pointer. Lines and points of items (body edges,
// sketch lines, construction edges) win within 5 px unless a surface covers
// them; otherwise the nearest surface of a requested kind. Items count as a
// depth-bias closer than they are, since they are drawn in front of the scan.

import * as THREE from 'three';

import type { SceneItem } from '@shared/protocol/generated/document-display';

import type { PickHit, ScreenPoint, Vec3 } from './api';
import type { CameraRig } from './CameraRig';
import type { ItemLayer } from './itemLayer';
import type { ScanMesh } from './scanMesh';
import { raycastScan } from './scanPicking';
import type { PickView } from './scanVisibility';

const LINE_PICK_PX = 5;
/** Lines count as visible up to this many pixels behind the surface at the pointer. */
const LINE_OCCLUSION_PX = 3;

const tuple = (vector: THREE.Vector3): Vec3 => [vector.x, vector.y, vector.z];

export interface PickScene {
  rig: CameraRig;
  size: { width: number; height: number };
  /** Null while the scan is hidden or not loaded. */
  scan: ScanMesh | null;
  scanMatrix: THREE.Matrix4;
  items: ItemLayer;
  /** Section clipping plane in part coordinates (three.js convention: kept side positive). */
  clippingPlane: THREE.Plane;
  sectionOn: boolean;
  /** Current depth bias of items in world units. */
  bias: number;
}

/** The section plane in scan-local coordinates with its normal towards the removed side. */
export function localCutPlane(scene: PickScene): THREE.Plane | null {
  if (!scene.sectionOn) return null;
  const toLocal = scene.scanMatrix.clone().invert();
  return scene.clippingPlane.clone().applyMatrix4(toLocal).negate();
}

/** Camera and scan placement as plain numbers for brush and lasso picking. */
export function pickViewOf(scene: PickScene): PickView {
  const { rig, size } = scene;
  const camera = rig.camera;
  camera.updateMatrixWorld();
  const toView = new THREE.Matrix4().multiplyMatrices(camera.matrixWorldInverse, scene.scanMatrix);
  const toClip = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, toView);
  const orthographic = rig.orthographicProjection;
  const cut = localCutPlane(scene);
  return {
    toClip: [...toClip.elements],
    toView: [...toView.elements],
    orthographic,
    width: size.width,
    height: size.height,
    pixelSize: orthographic
      ? rig.worldPerPixel(rig.target)
      : (2 * Math.tan((rig.fieldOfView * Math.PI) / 360)) / size.height,
    clip: cut ? [cut.normal.x, cut.normal.y, cut.normal.z, -cut.constant] : null,
  };
}

const raycaster = new THREE.Raycaster();

export function pickScene(
  scene: PickScene,
  at: ScreenPoint,
  kinds: readonly PickHit['kind'][],
): PickHit | null {
  const camera = scene.rig.camera;
  raycaster.setFromCamera(scene.rig.toNdc(at), camera);
  const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
  const depthOf = (point: THREE.Vector3) => point.clone().sub(camera.position).dot(forward);
  // Every surface under the pointer occludes lines, even kinds that were not asked for.
  const surfaces: { depth: number; hit: PickHit | null }[] = [];

  if (scene.scan) {
    const localRay = raycaster.ray.clone().applyMatrix4(scene.scanMatrix.clone().invert());
    const hit = raycastScan(scene.scan, localRay, localCutPlane(scene));
    if (hit) {
      const point = hit.point.applyMatrix4(scene.scanMatrix);
      surfaces.push({
        depth: depthOf(point),
        hit: kinds.includes('scan') ? { kind: 'scan', face: hit.face, point: tuple(point) } : null,
      });
    }
  }
  for (const hit of raycaster.intersectObjects(scene.items.surfaces(), false)) {
    const item = hit.object.userData.item as SceneItem | undefined;
    if (!item) continue;
    const body = !!item.bodyId && item.style !== 'construction' && item.style !== 'patch';
    if (body && scene.sectionOn && scene.clippingPlane.distanceToPoint(hit.point) < 0) continue;
    const point = tuple(hit.point);
    let pickHit: PickHit | null = null;
    if (body && kinds.includes('body')) {
      const faceIds = hit.object.userData.faceIds as Uint32Array | undefined;
      const face = faceIds?.[hit.faceIndex ?? 0] ?? 0;
      pickHit = { kind: 'body', bodyId: item.bodyId ?? '', face, point };
    } else if (kinds.includes('item')) {
      pickHit = { kind: 'item', key: item.key, owner: item.owner, point };
    }
    surfaces.push({ depth: depthOf(hit.point) - scene.bias, hit: pickHit });
  }
  surfaces.sort((a, b) => a.depth - b.depth);

  const line = scene.items.nearestLine(at, LINE_PICK_PX, camera, scene.size, kinds);
  if (line) {
    const depth = depthOf(new THREE.Vector3(...line.hit.point));
    const slack = LINE_OCCLUSION_PX * scene.rig.worldPerPixel(line.hit.point) + scene.bias;
    if (depth <= (surfaces[0]?.depth ?? Infinity) + slack) return line.hit;
  }
  return surfaces.find((surface) => surface.hit)?.hit ?? null;
}
