// What the sketch tool offers to automation clients (docs/AUTOMATION.md `toolInfo`):
// the closed section outlines a click fits, the joints a Ctrl click rounds and the
// entities, each with its position on screen, so an assistant can sketch by clicking
// like the user does.

import { useEffect, useRef } from 'react';

import type { SketchFrame } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { setToolInfoProvider } from '../../automation/toolInfo';
import { useViewport } from '../../viewport/api';
import { entityPolyline, pointDegrees } from './draftGeometry';
import { interiorPoint } from './sketchGestures';
import { shapeSizes } from './shapeSizes';
import { type Vec2, toPart } from './sketchMath';

interface Source {
  sketch: SketchParams;
  frame: SketchFrame | null;
  loops: readonly (readonly Vec2[])[];
  /** A gesture is being fitted. */
  busy: boolean;
}

export function useSketchToolInfo(source: Source): void {
  const viewport = useViewport();
  const latest = useRef(source);
  useEffect(() => {
    latest.current = source;
  });
  useEffect(() => {
    if (!viewport) return;
    return setToolInfoProvider(() => {
      const { sketch, frame, loops, busy } = latest.current;
      if (!frame) return null;
      const screen = (at: Vec2 | null) => (at ? viewport.worldToScreen(toPart(frame, at)) : null);
      const degrees = pointDegrees(sketch);
      return {
        tool: 'section-sketch',
        state: { job: busy },
        outlines: loops.map((loop, index) => {
          const at = interiorPoint(loop);
          return { index, at, screen: screen(at) };
        }),
        joints: sketch.points
          .filter((point) => degrees.get(point.id) === 2)
          .map((point) => ({
            id: point.id,
            entities: sketch.entities
              .filter((e) => e.type !== 'circle' && (e.start === point.id || e.end === point.id))
              .map((e) => e.id),
            screen: screen([point.x, point.y]),
          })),
        entities: sketch.entities.map((entity) => {
          const line = entityPolyline(sketch, entity.id);
          const at = line[Math.floor((line.length - 1) / 2)] ?? null;
          return { id: entity.id, type: entity.type, screen: screen(at) };
        }),
        shapes: sketch.shapes.map((shape) => ({ ...shape, sizes: shapeSizes(sketch, shape) })),
      };
    });
  }, [viewport]);
}
