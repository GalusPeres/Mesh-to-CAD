// Brush (B): paint faces under a screen-sized ring. Left drag adds, Ctrl + left
// drag removes; `[` `]` and Ctrl + wheel change the size. One stroke is one
// undo step. Picking is batched per animation frame, so a fast stroke costs at
// most one pick per sample and frame.

import type { ScreenPoint, Viewport, ViewportInteraction } from '../../viewport/api';
import { updateGesture } from '../gestureStore';
import { Stroke, withoutHidden } from '../selectionActions';
import { resizeBrush, selectionOptionsStore } from '../selectionOptions';
import { strokeSamples } from '../screenShapes';
import { clearOnEmptyClick, isClick } from './emptyClick';
import type { SelectionMode } from './types';

/** Samples are spaced at this fraction of the radius, so the painted band has no gaps. */
const SAMPLE_SPACING = 0.5;

export function createBrushMode(viewport: Viewport): SelectionMode {
  let stroke: Stroke | null = null;
  let last: ScreenPoint | null = null;
  let start: ScreenPoint | null = null;
  let pending: ScreenPoint[] = [];
  let frame = 0;

  const paint = () => {
    frame = 0;
    if (!stroke) return;
    const { brushRadius, visibleOnly } = selectionOptionsStore.getState();
    for (const point of pending) {
      const faces = viewport.pickScanFacesInCircle(point, brushRadius, { visibleOnly });
      if (faces.length) stroke.add(withoutHidden(faces));
    }
    pending = [];
  };

  const queue = (points: ScreenPoint[]) => {
    pending.push(...points);
    frame ||= requestAnimationFrame(paint);
  };

  const finish = () => {
    if (frame) cancelAnimationFrame(frame);
    paint();
    stroke?.finish();
    stroke = null;
    last = null;
  };

  const interaction: ViewportInteraction = {
    cursor: 'none',
    onPointerDown(event) {
      if (event.button !== 0 || event.alt) return false;
      stroke = new Stroke(event.ctrl ? 0 : 1);
      last = event.screen;
      start = event.screen;
      updateGesture({ pointer: event.screen, removing: event.ctrl });
      queue([event.screen]);
      return true;
    },
    onPointerMove(event) {
      updateGesture({ pointer: event.screen, removing: stroke ? stroke.value === 0 : event.ctrl });
      if (!stroke || !last) return false;
      const spacing = selectionOptionsStore.getState().brushRadius * SAMPLE_SPACING;
      queue(strokeSamples(last, event.screen, spacing));
      last = event.screen;
      return true;
    },
    onPointerUp(event) {
      const clicked = start !== null && isClick(start, event.screen);
      const removing = stroke?.value === 0;
      start = null;
      finish();
      if (clicked) clearOnEmptyClick(viewport, event.screen, removing);
      return true;
    },
    onWheel(event) {
      if (!event.ctrl) return false;
      resizeBrush(event.deltaY < 0 ? 1 : -1);
      return true;
    },
    onKeyDown(event) {
      if (event.key === '[' || event.key === ']') {
        resizeBrush(event.key === ']' ? 1 : -1);
        return true;
      }
      return false;
    },
  };

  return {
    interaction,
    busy: () => stroke !== null,
    cancel: finish,
    dispose: finish,
  };
}
