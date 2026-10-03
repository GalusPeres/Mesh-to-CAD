// Sizes of recognised shapes, read from their entities in the fixed order of
// `SketchShape` (the kernel stores no sizes, so typed and refitted values show).

import type { TFunction } from 'i18next';

import type { SketchParams, SketchShape } from '@shared/protocol/generated/sketch-params';

import type { Formatter } from '../../i18n/format';
import { pointOf, xy } from './draftGeometry';
import { lineLength } from './sketchMath';

const KEY = 'tools:sectionSketch';

export type ShapeSizes = Partial<
  Record<'diameter' | 'length' | 'width' | 'corner' | 'outer' | 'inner', number>
>;

export function shapeSizes(sketch: SketchParams, shape: SketchShape): ShapeSizes {
  const entities = shape.entities
    .map((id) => sketch.entities.find((entity) => entity.id === id))
    .filter((entity) => entity !== undefined);
  const radii = entities.flatMap((entity) => (entity.type === 'line' ? [] : [entity.radius]));
  const lengths = entities.flatMap((entity) =>
    entity.type === 'line'
      ? [lineLength(xy(pointOf(sketch, entity.start)), xy(pointOf(sketch, entity.end)))]
      : [],
  );
  const r = radii[0] ?? 0;
  switch (shape.kind) {
    case 'circle':
      return { diameter: 2 * r };
    case 'slot':
      return { length: (lengths[0] ?? 0) + 2 * r, width: 2 * r };
    case 'roundedRect': {
      const [long, short] = [...lengths.slice(0, 2)].sort((a, b) => b - a);
      return { length: (long ?? 0) + 2 * r, width: (short ?? 0) + 2 * r, corner: r };
    }
    case 'ringArm': {
      const middle = entities[Math.floor(entities.length / 2)];
      const corner = entities.find((entity, index) => entity.type === 'arc' && index % 2 === 1);
      return {
        outer: r,
        inner: middle && middle.type !== 'line' ? middle.radius : 0,
        corner: corner && corner.type !== 'line' ? corner.radius : 0,
      };
    }
  }
}

/** "7,75 × 4,50", "⌀ 7,25", "R 13,50 / 8,50". */
export function shapeSizeText(sketch: SketchParams, shape: SketchShape, format: Formatter): string {
  const size = shapeSizes(sketch, shape);
  const n = (value: number | undefined) => format.number(value ?? 0, 2);
  switch (shape.kind) {
    case 'circle':
      return `⌀ ${n(size.diameter)}`;
    case 'slot':
      return `${n(size.length)} × ${n(size.width)}`;
    case 'roundedRect':
      return `${n(size.length)} × ${n(size.width)} R ${n(size.corner)}`;
    case 'ringArm':
      return `R ${n(size.outer)} / ${n(size.inner)}`;
  }
}

/** "Langloch 3": kind and the shape's number. */
export function shapeLabel(shape: SketchShape, t: TFunction): string {
  return `${t(`${KEY}.shape.${shape.kind}`)} ${shape.id.slice(1)}`;
}
