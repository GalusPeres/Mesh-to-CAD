// Viewport side of the sketch tool: the overlay, the cut handle while the plane
// is chosen, and in sketch mode the camera along the plane (orbit locked, scan
// ghosted, DESIGN.md 6.5) and the pointer and key handling of the sketch tools.

import { useEffect, useRef } from 'react';

import type { EntityFitInfo, SketchFrame } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { resolveShortcut } from '../../app/commands/keymap';
import { SCENE_MIX } from '../../viewport/palette';
import { type ViewportPointerEvent, useViewport } from '../../viewport/api';
import { commands as sketchCommands } from './sketch.commands';
import { PaintStroke, type Project } from './sketchPicking';
import { type SectionDrawing, SketchScene } from './sketchScene';
import { type Vec2, type Vec3, rayToSketch } from './sketchMath';

export interface SketchHighlight {
  selected: string | null;
  pending: readonly string[];
  points: readonly Vec2[];
  gaps: readonly Vec2[];
}

export interface SketchPointerHandlers {
  /** A left click in sketch mode (not a painting stroke). */
  click: (cursor: Vec2, atPlane: Vec2 | null, alt: boolean) => void;
  /** Section points collected by a Shift+drag stroke. */
  paint: (points: Vec2[]) => void;
  /** Esc with a drawing step in progress; returns false when there is none. */
  abort: () => boolean;
}

export interface SketchViewportInput {
  step: 'plane' | 'sketch';
  section: SectionDrawing | null;
  frame: SketchFrame | null;
  sketch: SketchParams | null;
  fits: readonly EntityFitInfo[];
  highlight: SketchHighlight;
  /**
   * Plane step: cut position along the normal, moved with the arrow handle.
   * `revision` changes when the value is set other than by the handle (typed,
   * new plane), which places the handle anew; drags never rebuild it.
   */
  cut: { value: number; revision: number; change: (value: number, done: boolean) => void } | null;
  handlers: SketchPointerHandlers;
}

function isTextField(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}

function sectionPoints(section: SectionDrawing | null): Vec2[] {
  if (!section) return [];
  const source = section.folded ? [section.folded] : section.polylines;
  return source.flatMap((array) => {
    const points: Vec2[] = [];
    for (let i = 0; i + 1 < array.length; i += 2) points.push([array[i] ?? 0, array[i + 1] ?? 0]);
    return points;
  });
}

export function useSketchViewport(input: SketchViewportInput): { project: Project | null } {
  const viewport = useViewport();
  const scene = useRef<SketchScene | null>(null);
  const latest = useRef(input);

  useEffect(() => {
    latest.current = input;
  });

  // Declared first, so the drawing effects below find the scene in the same commit.
  useEffect(() => {
    if (!viewport) return;
    scene.current = new SketchScene(viewport.createOverlay());
    return () => {
      scene.current?.dispose();
      scene.current = null;
    };
  }, [viewport]);

  const { step, section, frame, sketch, fits, highlight } = input;
  useEffect(() => {
    scene.current?.showSection(section, step === 'sketch');
  }, [viewport, section, step]);

  useEffect(() => {
    scene.current?.showSketch(step === 'sketch' ? frame : null, sketch, fits, highlight);
  }, [viewport, step, frame, sketch, fits, highlight]);

  // Plane step: arrow handle on the cut position.
  const cutFrame = step === 'plane' && input.cut && frame && !frame.rotational ? frame : null;
  const cutKey = cutFrame
    ? JSON.stringify([cutFrame.origin, cutFrame.normal, input.cut?.revision ?? 0])
    : null;
  useEffect(() => {
    if (!viewport || !cutKey) return;
    const [origin, normal] = JSON.parse(cutKey) as [Vec3, Vec3];
    const handle = viewport.handles.arrow({
      origin,
      direction: normal,
      value: latest.current.cut?.value ?? 0,
      color: 'neutral',
      onChange: (value) => {
        if (typeof value === 'number') latest.current.cut?.change(value, false);
      },
      onCommit: (value) => {
        if (typeof value === 'number') latest.current.cut?.change(value, true);
      },
    });
    return () => handle.dispose();
  }, [viewport, cutKey]);

  // Sketch mode: look along the plane, lock orbiting, ghost the scan.
  const sketchFrame = step === 'sketch' ? frame : null;
  const frameKey = sketchFrame
    ? JSON.stringify([sketchFrame.origin, sketchFrame.normal, sketchFrame.xDir])
    : null;
  useEffect(() => {
    if (!viewport || !frameKey) return;
    const [origin, normal, xDir] = JSON.parse(frameKey) as [Vec3, Vec3, Vec3];
    viewport.camera.lookAlong(origin, normal, xDir);
    viewport.camera.setOrbitLocked(true);
    viewport.scan.setOpacity(SCENE_MIX.sketchGhostOpacity);
    return () => {
      viewport.camera.setOrbitLocked(false);
      viewport.scan.setOpacity(1);
    };
  }, [viewport, frameKey]);

  const project: Project | null = viewport ? (point) => viewport.worldToScreen(point) : null;

  useEffect(() => {
    if (!viewport || step !== 'sketch') return;
    let stroke: PaintStroke | null = null;
    const cursorOf = (event: ViewportPointerEvent): Vec2 => [event.screen.x, event.screen.y];
    return viewport.addInteraction({
      cursor: 'crosshair',
      onPointerDown: (event) => {
        const current = latest.current;
        if (event.button !== 0 || !current.frame) return false;
        if (event.shift) {
          stroke = new PaintStroke(sectionPoints(current.section), current.frame, (point) =>
            viewport.worldToScreen(point),
          );
          stroke.add(cursorOf(event));
          return true;
        }
        const ray = viewport.screenToRay(event.screen);
        const atPlane = rayToSketch(current.frame, ray.origin, ray.direction);
        current.handlers.click(cursorOf(event), atPlane, event.alt);
        return true;
      },
      onPointerMove: (event) => {
        if (!stroke) return false;
        stroke.add(cursorOf(event));
        return true;
      },
      onPointerUp: () => {
        if (!stroke) return false;
        const points = stroke.collected();
        stroke = null;
        if (points.length >= 2) latest.current.handlers.paint(points);
        return true;
      },
      onKeyDown: (event) => {
        if (isTextField(event.target) || event.repeat) return false;
        if (event.key === 'Escape') return latest.current.handlers.abort();
        const command = resolveShortcut(event, sketchCommands, {
          inTextField: false,
          sketchMode: true,
        });
        if (!command || (command.isEnabled && !command.isEnabled())) return false;
        void command.run();
        return true;
      },
    });
  }, [viewport, step]);

  return { project };
}
