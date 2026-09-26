// Three.js objects for scene items, drawn by semantic style (docs/DESIGN.md 6.5).
// The viewport knows nothing about feature types, only about styles.

import * as THREE from 'three';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';

import type { SceneItem, ScenePayload } from '@shared/protocol/generated/document-display';

import type { DepthBias } from './depthBias';
import { SCENE_COLORS, SCENE_MIX } from './palette';

/** Colours the scene takes from the UI theme. */
export interface ThemeColors {
  dark: boolean;
  text: string;
  textSecondary: string;
  accent: string;
  accentText: string;
  viewportBackground: string;
  bgApp: string;
  bgRaised: string;
  bgHover: string;
  borderStrong: string;
  /** CSS font stack of the UI, for labels drawn into textures. */
  font: string;
}

/** Line segments of an item for screen-space picking (6 floats per segment). */
export interface PickableLines {
  segments: Float32Array;
  ids: Uint32Array;
}

export interface DisplayObject {
  item: SceneItem;
  object: THREE.Object3D;
  lines: PickableLines | null;
  setTheme(theme: ThemeColors): void;
  setHighlight(on: boolean): void;
  /** A newer version is being computed: draw at half opacity (previewBody). */
  setStale(stale: boolean): void;
  dispose(): void;
}

export interface DisplayContext {
  bias: DepthBias;
  clipping: THREE.Plane[];
  theme: ThemeColors;
}

const HIGHLIGHT_EMISSIVE = 0.25;

function meshGeometry(payload: Extract<ScenePayload, { type: 'mesh' }>): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(payload.positions, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(payload.normals, 3));
  geometry.setIndex(new THREE.BufferAttribute(payload.indices, 1));
  geometry.computeBoundingSphere();
  geometry.computeBoundingBox();
  return geometry;
}

function surfaceMaterial(item: SceneItem, context: DisplayContext): THREE.MeshStandardMaterial {
  const construction = item.style === 'construction' || item.style === 'patch';
  const material = construction
    ? new THREE.MeshStandardMaterial({
        color: SCENE_COLORS.construction,
        transparent: true,
        opacity: item.style === 'patch' ? SCENE_MIX.patchFill : SCENE_MIX.constructionFill,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
    : new THREE.MeshStandardMaterial({
        color: SCENE_COLORS.body,
        roughness: 0.45,
        metalness: 0,
        side: THREE.DoubleSide,
      });
  if (!construction) material.clippingPlanes = context.clipping;
  context.bias.apply(material, construction ? 1.5 : 1);
  return material;
}

type LineStyle = { width: number; bias: number; color: (theme: ThemeColors) => string };

const LINE_STYLES: Partial<Record<SceneItem['style'], LineStyle>> = {
  bodyEdges: {
    width: 1,
    bias: 1.5,
    color: (theme) => (theme.dark ? SCENE_COLORS.bodyEdgesDark : SCENE_COLORS.bodyEdgesLight),
  },
  constructionEdges: { width: 2, bias: 1.5, color: () => SCENE_COLORS.construction },
  patch: { width: 1, bias: 1.5, color: () => SCENE_COLORS.construction },
  sketch: { width: 2, bias: 2, color: (theme) => theme.text },
  section: { width: 1.5, bias: 2, color: () => SCENE_COLORS.section },
};
const DEFAULT_LINE: LineStyle = { width: 1, bias: 1.5, color: (theme) => theme.text };

/** Lines of `width` CSS pixels; 1 px lines use plain GL lines. */
export function createLines(
  segments: Float32Array,
  width: number,
  color: string,
  bias: DepthBias,
  biasScale: number,
): { object: THREE.Object3D; material: LineMaterial | THREE.LineBasicMaterial } {
  if (width <= 1) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(segments, 3));
    geometry.computeBoundingSphere();
    const material = new THREE.LineBasicMaterial({ color });
    bias.apply(material, biasScale);
    const lines = new THREE.LineSegments(geometry, material);
    lines.raycast = () => undefined;
    return { object: lines, material };
  }
  const geometry = new LineSegmentsGeometry().setPositions(segments);
  const material = new LineMaterial({ color: new THREE.Color(color).getHex(), linewidth: width });
  bias.applyToFatLines(material, biasScale);
  const lines = new LineSegments2(geometry, material);
  lines.raycast = () => undefined;
  return { object: lines, material };
}

function linesObject(
  item: SceneItem,
  payload: Extract<ScenePayload, { type: 'lines' }>,
  context: DisplayContext,
): DisplayObject {
  const style = LINE_STYLES[item.style] ?? DEFAULT_LINE;
  const { object, material } = createLines(
    payload.segments,
    style.width,
    style.color(context.theme),
    context.bias,
    style.bias,
  );
  if (item.style === 'bodyEdges') material.clippingPlanes = context.clipping;
  let theme = context.theme;
  let highlighted = false;
  const paint = () => material.color.set(highlighted ? SCENE_COLORS.selection : style.color(theme));
  return {
    item,
    object,
    lines: { segments: payload.segments, ids: payload.ids },
    setTheme: (next) => {
      theme = next;
      paint();
    },
    setHighlight: (on) => {
      highlighted = on;
      paint();
    },
    setStale: (stale) => {
      material.transparent = stale;
      material.opacity = stale ? 0.5 : 1;
    },
    dispose: () => {
      (object as THREE.Mesh).geometry.dispose();
      material.dispose();
    },
  };
}

export function createDisplayObject(
  item: SceneItem,
  payload: ScenePayload,
  context: DisplayContext,
): DisplayObject | null {
  if (payload.type === 'mesh') {
    const geometry = meshGeometry(payload);
    const material = surfaceMaterial(item, context);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData = { item, faceIds: payload.faceIds };
    const opacity = material.opacity;
    return {
      item,
      object: mesh,
      lines: null,
      setTheme: () => undefined,
      setHighlight: (on) => {
        material.emissive.set(on ? SCENE_COLORS.selection : 0x000000);
        material.emissiveIntensity = on ? HIGHLIGHT_EMISSIVE : 0;
      },
      setStale: (stale) => {
        material.transparent = stale || opacity < 1;
        material.opacity = stale ? opacity * 0.5 : opacity;
        material.needsUpdate = true;
      },
      dispose: () => {
        geometry.dispose();
        material.dispose();
      },
    };
  }
  if (payload.type === 'lines') return linesObject(item, payload, context);
  if (payload.type === 'points') {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(payload.positions, 3));
    geometry.computeBoundingSphere();
    const colorOf = (theme: ThemeColors) =>
      item.style === 'sectionPoints' ? SCENE_COLORS.section : theme.textSecondary;
    const material = new THREE.PointsMaterial({
      color: colorOf(context.theme),
      size: 3,
      sizeAttenuation: false,
    });
    context.bias.apply(material, 2);
    const points = new THREE.Points(geometry, material);
    points.userData = { item };
    let theme = context.theme;
    let highlighted = false;
    const paint = () => material.color.set(highlighted ? SCENE_COLORS.selection : colorOf(theme));
    return {
      item,
      object: points,
      lines: null,
      setTheme: (next) => {
        theme = next;
        paint();
      },
      setHighlight: (on) => {
        highlighted = on;
        paint();
      },
      setStale: () => undefined,
      dispose: () => {
        geometry.dispose();
        material.dispose();
      },
    };
  }
  return null;
}

/** One object per style with a one-element payload, to compile their shaders early. */
export function warmUpObjects(context: DisplayContext): DisplayObject[] {
  const triangle = new Float32Array(9);
  const mesh = (key: string): ScenePayload => ({
    type: 'mesh',
    key,
    positions: triangle,
    indices: new Uint32Array([0, 1, 2]),
    normals: triangle,
    faceIds: new Uint32Array(1),
  });
  const lines = (key: string): ScenePayload => ({
    type: 'lines',
    key,
    segments: new Float32Array(6),
    ids: new Uint32Array(1),
    faces: null,
  });
  const styles: [SceneItem['style'], SceneItem['kind'], ScenePayload][] = [
    ['body', 'mesh', mesh('body')],
    ['construction', 'mesh', mesh('construction')],
    ['bodyEdges', 'lines', lines('bodyEdges')],
    ['constructionEdges', 'lines', lines('constructionEdges')],
    ['sketch', 'lines', lines('sketch')],
    ['section', 'lines', lines('section')],
    ['sketchPoints', 'points', { type: 'points', key: 'points', positions: new Float32Array(3) }],
  ];
  return styles.flatMap(([style, kind, payload]) => {
    const item: SceneItem = { key: style, kind, style, owner: '', bodyId: 'warm-up' };
    const object = createDisplayObject(item, payload, context);
    return object ? [object] : [];
  });
}
