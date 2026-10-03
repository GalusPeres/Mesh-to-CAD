// What the sketch tool draws in the viewport (DESIGN.md 6.5): the section while
// the plane is chosen, and in sketch mode the entities coloured pass/fail with
// their deviation, the selected entity, the section points, open ends, the points
// of a pending drawing step and what a click would act on (the outline or joint
// under the pointer). Everything lives in one tool overlay and is drawn on top.

import * as THREE from 'three';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';

import type { EntityFitInfo, SketchFrame } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import type { Overlay } from '../../viewport/api';
import { SCENE_COLORS } from '../../viewport/palette';
import type { DeviationLabel } from './deviationLabels';
import { entityPolyline } from './draftGeometry';
import { disposeMap, label } from './sketchLabels';
import { type Vec2, toPart } from './sketchMath';

export interface SectionDrawing {
  frame: SketchFrame;
  polylines: readonly Float32Array[];
  closed: readonly boolean[];
  folded: Float32Array | null;
}

export interface SketchHighlight {
  /** The selected entities (one entity, or all entities of a selected shape). */
  selected: readonly string[];
  pending: readonly string[];
  points: readonly Vec2[];
  gaps: readonly Vec2[];
  /** The outline a click would fit, or the joint a Ctrl click would round. */
  outline: readonly Vec2[] | null;
  joint: Vec2 | null;
  labels: readonly DeviationLabel[];
}

interface Theme {
  text: string;
  textSecondary: string;
  accentText: string;
  bgApp: string;
  font: string;
}

function readTheme(): Theme {
  const style = getComputedStyle(document.documentElement);
  const token = (name: string) => style.getPropertyValue(name).trim();
  return {
    text: token('--text'),
    textSecondary: token('--text-secondary'),
    accentText: token('--accent-text'),
    bgApp: token('--bg-app'),
    font: getComputedStyle(document.body).fontFamily,
  };
}

function material(color: string): THREE.LineBasicMaterial {
  return new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true });
}

function pointsMaterial(color: string, size: number): THREE.PointsMaterial {
  return new THREE.PointsMaterial({
    color,
    size,
    sizeAttenuation: false,
    depthTest: false,
    transparent: true,
  });
}

function strip(frame: SketchFrame, points: readonly Vec2[], color: string): THREE.Line {
  const positions = new Float32Array(points.flatMap((point) => toPart(frame, point)));
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const line = new THREE.Line(geometry, material(color));
  line.renderOrder = 10;
  return line;
}

/** Entities: 2 px lines (DESIGN.md 6.5) drawn above the section points they lie on. */
const ENTITY_WIDTH_PX = 2;

function entityLine(frame: SketchFrame, points: readonly Vec2[], color: string): LineSegments2 {
  const part = points.map((point) => toPart(frame, point));
  const positions = part.slice(1).flatMap((end, k) => [...(part[k] ?? end), ...end]);
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions(positions);
  const material = new LineMaterial({
    color,
    linewidth: ENTITY_WIDTH_PX,
    depthTest: false,
    transparent: true,
  });
  const line = new LineSegments2(geometry, material);
  line.frustumCulled = false;
  line.raycast = () => undefined;
  line.renderOrder = 12;
  return line;
}

function dots(
  frame: SketchFrame,
  points: readonly Vec2[],
  color: string,
  size: number,
  order = 14,
): THREE.Points {
  const positions = new Float32Array(points.flatMap((point) => toPart(frame, point)));
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const cloud = new THREE.Points(geometry, pointsMaterial(color, size));
  cloud.renderOrder = order;
  return cloud;
}

function packed(array: Float32Array): Vec2[] {
  const result: Vec2[] = [];
  for (let i = 0; i + 1 < array.length; i += 2) result.push([array[i] ?? 0, array[i + 1] ?? 0]);
  return result;
}

export class SketchScene {
  private readonly theme = readTheme();
  private readonly section = new THREE.Group();
  private readonly sketch = new THREE.Group();

  constructor(private readonly overlay: Overlay) {
    overlay.add(this.section);
    overlay.add(this.sketch);
  }

  /** The cut while the plane is chosen (green), or its points in sketch mode (grey). */
  showSection(drawing: SectionDrawing | null, sketchMode: boolean): void {
    clear(this.section);
    if (drawing) {
      const color = sketchMode ? this.theme.textSecondary : SCENE_COLORS.section;
      drawing.polylines.forEach((polyline, index) => {
        const points = packed(polyline);
        if (!sketchMode) {
          const closed = drawing.closed[index] && points[0] ? [...points, points[0]] : points;
          this.section.add(strip(drawing.frame, closed, color));
        }
        this.section.add(dots(drawing.frame, points, color, 3, 11));
      });
      if (drawing.folded && !sketchMode)
        this.section.add(dots(drawing.frame, packed(drawing.folded), color, 2, 11));
    }
    this.redraw(this.section);
  }

  showSketch(
    frame: SketchFrame | null,
    sketch: SketchParams | null,
    fits: readonly EntityFitInfo[],
    highlight: SketchHighlight,
  ): void {
    clear(this.sketch);
    if (frame && sketch) {
      const verdict = new Map(fits.map((fit) => [fit.entity, fit.passed]));
      if (highlight.outline) {
        const outline = highlight.outline;
        this.sketch.add(strip(frame, [...outline, ...outline.slice(0, 1)], this.theme.accentText));
      }
      for (const entity of sketch.entities) {
        const passed = verdict.get(entity.id);
        const color =
          highlight.selected.includes(entity.id) || highlight.pending.includes(entity.id)
            ? this.theme.accentText
            : passed === false
              ? SCENE_COLORS.fail
              : passed === true
                ? SCENE_COLORS.pass
                : this.theme.text;
        this.sketch.add(entityLine(frame, entityPolyline(sketch, entity.id), color));
      }
      if (highlight.points.length)
        this.sketch.add(dots(frame, highlight.points, this.theme.accentText, 7));
      if (highlight.gaps.length) this.sketch.add(dots(frame, highlight.gaps, SCENE_COLORS.fail, 9));
      if (highlight.joint)
        this.sketch.add(dots(frame, [highlight.joint], this.theme.accentText, 9));
      for (const item of highlight.labels) {
        const color =
          item.passed === false
            ? SCENE_COLORS.fail
            : item.passed
              ? SCENE_COLORS.pass
              : this.theme.text;
        const text = item.value < 0.0995 ? item.value.toFixed(3) : item.value.toFixed(2);
        this.sketch.add(
          label(frame, item.at, text, { color, outline: this.theme.bgApp, font: this.theme.font }),
        );
      }
    }
    this.redraw(this.sketch);
  }

  /** Adding a group again keeps it in place and makes the viewport render a new frame. */
  private redraw(group: THREE.Group): void {
    this.overlay.add(group);
  }

  dispose(): void {
    clear(this.section);
    clear(this.sketch);
    this.overlay.dispose();
  }
}

function clear(group: THREE.Group): void {
  for (const child of [...group.children]) {
    group.remove(child);
    if (
      child instanceof THREE.Line ||
      child instanceof THREE.Points ||
      child instanceof LineSegments2
    ) {
      const drawn = child as THREE.Mesh<THREE.BufferGeometry, THREE.Material>;
      drawn.geometry.dispose();
      disposeMap(drawn.material);
      drawn.material.dispose();
    }
  }
}
