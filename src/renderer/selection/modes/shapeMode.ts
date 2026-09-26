// Lasso (L) and rectangle: drag a screen shape; on release every face inside
// it is added (Ctrl: removed). Without Durch das Teil only visible faces count.

import type { ScreenPoint, Viewport, ViewportInteraction } from '../../viewport/api';
import { updateGesture } from '../gestureStore';
import { reportFailure } from '../reportFailure';
import { currentScan, setSelected, withoutHidden } from '../selectionActions';
import { selectionOptionsStore } from '../selectionOptions';
import { LassoPath, polygonArea, rectanglePolygon } from '../screenShapes';
import { clearOnEmptyClick, isClick } from './emptyClick';
import type { SelectionMode } from './types';

/** Shapes smaller than this (square pixels) are treated as a click and ignored. */
const MIN_AREA_PX = 9;

export type ShapeKind = 'lasso' | 'rectangle';

export function createShapeMode(viewport: Viewport, shape: ShapeKind): SelectionMode {
  let lasso: LassoPath | null = null;
  let from: ScreenPoint | null = null;
  let to: ScreenPoint | null = null;
  let removing = false;
  let disposed = false;

  const reset = () => {
    lasso = null;
    from = null;
    to = null;
    updateGesture({ lasso: null, rectangle: null });
  };

  const select = async (polygon: Float32Array, remove: boolean) => {
    const scanKey = currentScan()?.key;
    if (!scanKey || polygonArea(polygon) < MIN_AREA_PX) return;
    const visibleOnly = !selectionOptionsStore.getState().throughPart;
    try {
      const faces = await viewport.pickScanFacesInPolygon(polygon, { visibleOnly });
      // The scan may have changed while the faces were collected.
      if (disposed || currentScan()?.key !== scanKey || !faces.length) return;
      setSelected(withoutHidden(faces), remove ? 0 : 1);
    } catch (error) {
      reportFailure(error);
    }
  };

  const interaction: ViewportInteraction = {
    cursor: 'crosshair',
    onPointerDown(event) {
      if (event.button !== 0 || event.alt) return false;
      removing = event.ctrl;
      if (shape === 'lasso') {
        lasso = new LassoPath();
        lasso.add(event.screen);
        updateGesture({ lasso: lasso.polygon(), removing });
      } else {
        from = event.screen;
        to = event.screen;
        updateGesture({ rectangle: { from, to }, removing });
      }
      return true;
    },
    onPointerMove(event) {
      updateGesture({ pointer: event.screen });
      if (lasso) {
        if (lasso.add(event.screen)) updateGesture({ lasso: lasso.polygon() });
        return true;
      }
      if (from) {
        to = event.screen;
        updateGesture({ rectangle: { from, to } });
        return true;
      }
      updateGesture({ removing: event.ctrl });
      return false;
    },
    onPointerUp(event) {
      const clicked =
        from !== null && to !== null ? isClick(from, to) : lasso !== null && lasso.pointCount <= 1;
      const polygon = lasso ? lasso.polygon() : from && to ? rectanglePolygon(from, to) : null;
      const remove = removing;
      reset();
      if (clicked) clearOnEmptyClick(viewport, event.screen, remove);
      else if (polygon && polygon.length >= 6) void select(polygon, remove);
      return true;
    },
  };

  return {
    interaction,
    busy: () => lasso !== null || from !== null,
    cancel: reset,
    dispose: () => {
      disposed = true;
      reset();
    },
  };
}
