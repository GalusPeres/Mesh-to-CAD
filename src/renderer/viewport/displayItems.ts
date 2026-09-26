// Three.js objects for scene items, drawn by semantic style (docs/DESIGN.md 6.5).
// The viewport knows nothing about feature types, only about styles.

import * as THREE from 'three';

import type { SceneItem, ScenePayload } from '@shared/protocol/generated/document-display';

import { SCENE_COLORS, SCENE_MIX } from './palette';

/** Colours the scene takes from the UI theme. */
export interface ThemeColors {
  dark: boolean;
  text: string;
  textSecondary: string;
  viewportBackground: string;
}

export interface DisplayObject {
  item: SceneItem;
  object: THREE.Object3D;
  dispose(): void;
}

function meshGeometry(payload: Extract<ScenePayload, { type: 'mesh' }>): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(payload.positions, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(payload.normals, 3));
  geometry.setIndex(new THREE.BufferAttribute(payload.indices, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

function surfaceMaterial(item: SceneItem): THREE.Material {
  if (item.style === 'construction' || item.style === 'patch') {
    return new THREE.MeshStandardMaterial({
      color: SCENE_COLORS.construction,
      transparent: true,
      opacity: item.style === 'patch' ? SCENE_MIX.patchFill : SCENE_MIX.constructionFill,
      depthWrite: false,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    });
  }
  // Bodies sit within a tenth of a millimetre of the scan; the offset keeps them
  // in front of it instead of flickering (z-fighting).
  return new THREE.MeshStandardMaterial({
    color: SCENE_COLORS.body,
    roughness: 0.45,
    metalness: 0,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1,
  });
}

function lineColor(item: SceneItem, theme: ThemeColors): string {
  switch (item.style) {
    case 'bodyEdges':
      return theme.dark ? SCENE_COLORS.bodyEdgesDark : SCENE_COLORS.bodyEdgesLight;
    case 'constructionEdges':
    case 'patch':
      return SCENE_COLORS.construction;
    case 'section':
      return SCENE_COLORS.section;
    default:
      return theme.text;
  }
}

export function createDisplayObject(
  item: SceneItem,
  payload: ScenePayload,
  theme: ThemeColors,
): DisplayObject | null {
  if (payload.type === 'mesh') {
    const geometry = meshGeometry(payload);
    const material = surfaceMaterial(item);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData = { item, faceIds: payload.faceIds };
    return { item, object: mesh, dispose: () => (geometry.dispose(), material.dispose()) };
  }
  if (payload.type === 'lines') {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(payload.segments, 3));
    const material = new THREE.LineBasicMaterial({ color: lineColor(item, theme) });
    const lines = new THREE.LineSegments(geometry, material);
    lines.userData = { item, ids: payload.ids };
    return { item, object: lines, dispose: () => (geometry.dispose(), material.dispose()) };
  }
  if (payload.type === 'points') {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(payload.positions, 3));
    const color = item.style === 'sectionPoints' ? SCENE_COLORS.section : theme.textSecondary;
    const material = new THREE.PointsMaterial({ color, size: 3, sizeAttenuation: false });
    const points = new THREE.Points(geometry, material);
    points.userData = { item };
    return { item, object: points, dispose: () => (geometry.dispose(), material.dispose()) };
  }
  return null;
}
