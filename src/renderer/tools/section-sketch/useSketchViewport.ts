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
import { type SectionDrawing, type SketchHighlight, SketchScene } from './sketchScene';
import { type Vec2, type Vec3, distance, rayToSketch, toPart } from './sketchMath';

export type { SketchHighlight } from './sketchScene';

/** Where the pointer is: screen position, the point on the sketch plane, modifiers. */
export interface SketchPointer {
  cursor: Vec2;
  atPlane: Vec2 | null;
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
}

export interface SketchPointerHandlers {
  /** A left click in sketch mode (not a stroke), Ctrl held or not. */
  click: (pointer: SketchPointer) => void;
  /** Section points collected by a Shift+drag stroke. */
  paint: (points: Vec2[]) => void;
  /** The screen path of a Ctrl+drag stroke. */
  stroke?: (path: Vec2[]) => void;
  /** The pointer moved without a button pressed. */
  hover?: (pointer: SketchPointer) => void;
  /** Esc with a drawing step in progress; returns false when there is none. */
  abort: () => boolean;
}

/** A Ctrl stroke shorter than this (px) is a Ctrl click. */
const CLICK_PX = 4;
/** The camera turns to the sketch plane in 250 ms (DESIGN.md 6.5), then frames the section. */
const TURN_MS = 300;

/** Bounding box of the section in part coordinates, and its centre. */
function sectionBox(
  section: SectionDrawing | null,
  frame: SketchFrame | null,
): { min: Vec3; max: Vec3; center: Vec3 } | null {
  const points = sectionPoints(section);
  if (!frame || points.length === 0) return null;
  const us = points.map((p) => p[0]);
  const vs = points.map((p) => p[1]);
  const corners = [Math.min(...us), Math.max(...us)].flatMap((u) =>
    [Math.min(...vs), Math.max(...vs)].map((v) => toPart(frame, [u, v])),
  );
  const axis = (k: 0 | 1 | 2) => corners.map((corner) => corner[k]);
  const min: Vec3 = [Math.min(...axis(0)), Math.min(...axis(1)), Math.min(...axis(2))];
  const max: Vec3 = [Math.max(...axis(0)), Math.max(...axis(1)), Math.max(...axis(2))];
  return {
    min,
    max,
    center: [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2],
  };
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
    const box = sectionBox(latest.current.section, latest.current.frame);
    viewport.camera.lookAlong(box ? box.center : origin, normal, xDir);
    viewport.camera.setOrbitLocked(true);
    viewport.scan.setOpacity(SCENE_MIX.sketchGhostOpacity);
    // The plane's fill would cover the section: the sketch takes its place.
    const plane = latest.current.sketch?.section;
    const source =
      plane?.type === 'planar' && plane.plane.type === 'feature' ? plane.plane.feature : null;
    if (source) viewport.setOwnerHidden(source);
    // Frame the section once the camera has turned (fitting keeps the orientation).
    const fit = box ? setTimeout(() => viewport.camera.fitBox(box.min, box.max), TURN_MS) : 0;
    return () => {
      clearTimeout(fit);
      if (source) viewport.setOwnerHidden(null);
      viewport.camera.setOrbitLocked(false);
      viewport.scan.setOpacity(1);
    };
  }, [viewport, frameKey]);

  const project: Project | null = viewport ? (point) => viewport.worldToScreen(point) : null;

  useEffect(() => {
    if (!viewport || step !== 'sketch') return;
    let stroke: PaintStroke | null = null;
    let path: Vec2[] | null = null;
    const cursorOf = (event: ViewportPointerEvent): Vec2 => [event.screen.x, event.screen.y];
    const pointerOf = (event: ViewportPointerEvent): SketchPointer => {
      const frame = latest.current.frame;
      const ray = viewport.screenToRay(event.screen);
      return {
        cursor: cursorOf(event),
        atPlane: frame ? rayToSketch(frame, ray.origin, ray.direction) : null,
        ctrl: event.ctrl,
        alt: event.alt,
        shift: event.shift,
      };
    };
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
        if (event.ctrl) {
          path = [cursorOf(event)];
          return true;
        }
        current.handlers.click(pointerOf(event));
        return true;
      },
      onPointerMove: (event) => {
        if (stroke) {
          stroke.add(cursorOf(event));
          return true;
        }
        if (path) {
          path.push(cursorOf(event));
          return true;
        }
        if (event.buttons === 0) latest.current.handlers.hover?.(pointerOf(event));
        return false;
      },
      onPointerUp: (event) => {
        if (path) {
          const done = path;
          path = null;
          const start = done[0] as Vec2;
          const short = done.every((cursor) => distance(cursor, start) < CLICK_PX);
          if (short) latest.current.handlers.click(pointerOf(event));
          else latest.current.handlers.stroke?.(done);
          return true;
        }
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
