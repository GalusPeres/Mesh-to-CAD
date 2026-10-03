// Text labels drawn in the 3D view at a constant pixel size: one point sprite per
// label whose texture holds the text in its upper half, so the text sits just above
// the anchor and stays legible at every zoom (Points have a fixed size in pixels).

import * as THREE from 'three';

import type { SketchFrame } from '@shared/protocol/generated/sketch';

import { type Vec2, toPart } from './sketchMath';

const SIZE_PX = 56;
const FONT_PX = 12;
/** Texture pixels per screen pixel (sharp on high-density screens). */
const SCALE = 2;

export interface LabelStyle {
  color: string;
  /** Outline for legibility on the scan (DESIGN.md 6.5: 1 px in `--bg-app`). */
  outline: string;
  font: string;
}

function texture(text: string, style: LabelStyle): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = SIZE_PX * SCALE;
  const context = canvas.getContext('2d');
  if (context) {
    context.scale(SCALE, SCALE);
    context.font = `${FONT_PX}px ${style.font}`;
    context.textAlign = 'center';
    context.textBaseline = 'bottom';
    context.lineWidth = 3;
    context.strokeStyle = style.outline;
    context.fillStyle = style.color;
    const x = SIZE_PX / 2;
    const y = SIZE_PX / 2 - 3;
    context.strokeText(text, x, y);
    context.fillText(text, x, y);
  }
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  return map;
}

export function label(frame: SketchFrame, at: Vec2, text: string, style: LabelStyle): THREE.Points {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.BufferAttribute(new Float32Array(toPart(frame, at)), 3),
  );
  const material = new THREE.PointsMaterial({
    map: texture(text, style),
    size: SIZE_PX,
    sizeAttenuation: false,
    transparent: true,
    depthTest: false,
  });
  const points = new THREE.Points(geometry, material);
  points.renderOrder = 13;
  return points;
}

/** Releases the texture of a label (materials of other drawings have none). */
export function disposeMap(material: THREE.Material): void {
  if (material instanceof THREE.PointsMaterial) material.map?.dispose();
}
