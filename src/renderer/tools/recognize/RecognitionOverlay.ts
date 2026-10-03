// The recognised features in the viewport: the outline of every feature at its foot
// and at its top, coloured by role (raised, pocket, hole, free profile), and one label
// per group with its size that stays the same size on screen. Unchecked features
// are drawn grey, the hovered group in the hover colour. Labels on faces turned away
// from the camera are hidden, as their outlines are.

import * as THREE from 'three';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';

import type { RecognizeResult } from '@shared/protocol/generated/recognize';

import type { Overlay, ScreenPoint, Vec3 } from '../../viewport/api';
import { RECOGNITION_COLORS } from '../../viewport/palette';
import { type FeatureRole, roleOf } from './model';

/** Depth bias of the outlines in units of the scene bias (they lie on the scan). */
const LINE_BIAS = 3;
const LINE_WIDTH_PX = 2.5;
const LABEL_HEIGHT_PX = 18;
const LABEL_FONT_PX = 12;
const LABEL_PADDING_PX = 5;
/** Canvas pixels per screen pixel, for crisp text on high-density screens. */
const LABEL_SCALE = 2;
const UNCHECKED_OPACITY = 0.55;
/** A label hides once its face turns away beyond this cosine to the view direction. */
const AWAY = 0.1;

interface Label {
  feature: number;
  sprite: THREE.Sprite;
  material: THREE.SpriteMaterial;
  texture: THREE.Texture;
  position: Vec3;
  widthPx: number;
  /** Opacity when its face is turned towards the camera. */
  opacity: number;
  /** Drawn in the last frame (its face was turned towards the camera). */
  shown: boolean;
}

function rgb(hex: string): [number, number, number] {
  const color = new THREE.Color(hex);
  return [color.r, color.g, color.b];
}

function roleColor(role: FeatureRole, profile: boolean): string {
  if (profile) return RECOGNITION_COLORS.profile;
  return RECOGNITION_COLORS[role];
}

function labelTexture(text: string): { texture: THREE.Texture; widthPx: number } {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  const font = `600 ${LABEL_FONT_PX * LABEL_SCALE}px system-ui, sans-serif`;
  let widthPx = LABEL_HEIGHT_PX;
  if (context) {
    context.font = font;
    widthPx = Math.ceil(context.measureText(text).width / LABEL_SCALE) + 2 * LABEL_PADDING_PX;
  }
  canvas.width = widthPx * LABEL_SCALE;
  canvas.height = LABEL_HEIGHT_PX * LABEL_SCALE;
  if (context) {
    // Resizing the canvas resets the context state.
    context.font = font;
    context.fillStyle = RECOGNITION_COLORS.labelBackground;
    context.globalAlpha = 0.82;
    context.beginPath();
    context.roundRect(0, 0, canvas.width, canvas.height, 4 * LABEL_SCALE);
    context.fill();
    context.globalAlpha = 1;
    context.fillStyle = RECOGNITION_COLORS.labelText;
    context.textBaseline = 'middle';
    context.textAlign = 'center';
    context.fillText(text, canvas.width / 2, canvas.height / 2 + LABEL_SCALE);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { texture, widthPx };
}

const scratch = new THREE.Vector3();

/** World units per screen pixel at a point (perspective and orthographic cameras). */
function unitsPerPixel(
  renderer: THREE.WebGLRenderer,
  camera: THREE.Camera,
  point: THREE.Vector3,
): number {
  const height = Math.max(renderer.domElement.clientHeight, 1);
  if ((camera as THREE.PerspectiveCamera).isPerspectiveCamera) {
    const perspective = camera as THREE.PerspectiveCamera;
    // Depth along the view direction, not the distance to the eye.
    const depth = -scratch.copy(point).applyMatrix4(perspective.matrixWorldInverse).z;
    const fov = THREE.MathUtils.degToRad(perspective.fov);
    return (2 * Math.max(depth, 1e-6) * Math.tan(fov / 2)) / (height * perspective.zoom);
  }
  const orthographic = camera as THREE.OrthographicCamera;
  return (orthographic.top - orthographic.bottom) / orthographic.zoom / height;
}

export class RecognitionOverlay {
  private readonly geometry = new LineSegmentsGeometry();
  private readonly material: LineMaterial;
  /** Feature index of every outline segment. */
  private readonly segmentFeature: Uint32Array;
  private readonly labels: Label[] = [];

  /**
   * @param labelTexts Per feature, its label or null for none (one label per group).
   */
  constructor(
    private readonly overlay: Overlay,
    private readonly result: RecognizeResult,
    labelTexts: readonly (string | null)[],
  ) {
    const { outlines, outlineOffsets, features, planes } = result;
    const positions: number[] = [];
    const owners: number[] = [];
    for (let ring = 0; ring + 1 < outlineOffsets.length; ring += 1) {
      const start = outlineOffsets[ring] ?? 0;
      const end = outlineOffsets[ring + 1] ?? start;
      for (let i = start; i < end; i += 1) {
        const next = i + 1 < end ? i + 1 : start;
        for (const point of [i, next]) {
          positions.push(
            outlines[3 * point] ?? 0,
            outlines[3 * point + 1] ?? 0,
            outlines[3 * point + 2] ?? 0,
          );
        }
        owners.push(Math.floor(ring / 2));
      }
    }
    this.segmentFeature = Uint32Array.from(owners);
    this.geometry.setPositions(positions);
    this.material = new LineMaterial({ vertexColors: true, linewidth: LINE_WIDTH_PX });
    overlay.applyFatLineDepthBias(this.material, LINE_BIAS);
    const lines = new LineSegments2(this.geometry, this.material);
    lines.frustumCulled = false;
    lines.raycast = () => undefined;
    lines.renderOrder = 10;
    overlay.add(lines);

    const forward = new THREE.Vector3();
    features.forEach((feature, index) => {
      const text = labelTexts[index];
      if (!text) return;
      const { texture, widthPx } = labelTexture(text);
      const material = new THREE.SpriteMaterial({
        map: texture,
        depthTest: false,
        depthWrite: false,
        transparent: true,
      });
      const sprite = new THREE.Sprite(material);
      sprite.position.set(...feature.label);
      sprite.renderOrder = 20;
      sprite.raycast = () => undefined;
      const normal = new THREE.Vector3(...(planes[feature.plane]?.normal ?? [0, 0, 1]));
      const label: Label = {
        feature: index,
        sprite,
        material,
        texture,
        position: feature.label,
        widthPx,
        opacity: 1,
        shown: true,
      };
      sprite.onBeforeRender = (renderer, _scene, camera) => {
        const perPixel = unitsPerPixel(renderer, camera, sprite.position);
        sprite.scale.set(widthPx * perPixel, LABEL_HEIGHT_PX * perPixel, 1);
        sprite.updateMatrixWorld();
        // Material values are uploaded after this call, so this frame already uses them.
        label.shown = normal.dot(camera.getWorldDirection(forward)) < AWAY;
        material.opacity = label.shown ? label.opacity : 0;
      };
      overlay.add(sprite);
      this.labels.push(label);
    });
  }

  /**
   * Colour every feature by its role, grey when its group is unchecked, in the hover
   * colour when its group is hovered.
   */
  paint(groupOf: readonly number[], checked: ReadonlySet<number>, hovered: number | null): void {
    const featureColor = this.result.features.map((feature, index) => {
      const group = groupOf[index] ?? -1;
      if (group === hovered) return rgb(RECOGNITION_COLORS.hover);
      if (!checked.has(group)) return rgb(RECOGNITION_COLORS.unchecked);
      return rgb(roleColor(roleOf(feature), feature.shape === 'profile'));
    });
    const colors = new Float32Array(this.segmentFeature.length * 6);
    this.segmentFeature.forEach((feature, segment) => {
      const color = featureColor[feature];
      if (!color) return;
      colors.set(color, segment * 6);
      colors.set(color, segment * 6 + 3);
    });
    this.geometry.setColors(colors);
    for (const label of this.labels) {
      const group = groupOf[label.feature] ?? -1;
      label.material.color.set(
        group === hovered ? RECOGNITION_COLORS.hover : RECOGNITION_COLORS.labelPlain,
      );
      label.opacity = checked.has(group) || group === hovered ? 1 : UNCHECKED_OPACITY;
    }
  }

  /** The feature whose label is under a screen point, if any. */
  labelAt(at: ScreenPoint, project: (point: Vec3) => ScreenPoint | null): number | null {
    for (let index = this.labels.length - 1; index >= 0; index -= 1) {
      const label = this.labels[index];
      if (!label?.shown) continue;
      const centre = project(label.position);
      if (!centre) continue;
      const inside =
        Math.abs(at.x - centre.x) <= label.widthPx / 2 &&
        Math.abs(at.y - centre.y) <= LABEL_HEIGHT_PX / 2;
      if (inside) return label.feature;
    }
    return null;
  }

  dispose(): void {
    this.overlay.dispose();
    this.geometry.dispose();
    this.material.dispose();
    for (const label of this.labels) {
      label.material.dispose();
      label.texture.dispose();
    }
  }
}
