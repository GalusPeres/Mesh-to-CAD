// The selection layer of the viewport: runs the active selection mode, keeps the
// viewport's selection in step with the store, draws the brush ring, lasso and
// rectangle over the canvas, and shows the options of the active mode.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import type { ViewportOverlay } from '../app/extensions';
import { useTools } from '../state/toolStore';
import { useViewport } from '../viewport/api';
import { SCENE_COLORS } from '../viewport/palette';
import { updateGesture, useGesture } from './gestureStore';
import { SelectionOptionsBar } from './SelectionOptionsBar';
import styles from './SelectionLayer.module.css';
import {
  installSelection,
  isSelectionModeId,
  leaveModeWithoutScan,
  runSelectionMode,
  startViewportSync,
} from './selectionRuntime';
import { useSelectionOptions } from './selectionOptions';

function polygonPoints(polygon: Float32Array): string {
  const points: string[] = [];
  for (let index = 0; index + 1 < polygon.length; index += 2) {
    points.push(`${polygon[index]},${polygon[index + 1]}`);
  }
  return points.join(' ');
}

/** Brush ring, lasso path and rectangle in canvas pixels. */
function GestureDrawing({ mode }: { mode: string | null }) {
  const pointer = useGesture((state) => state.pointer);
  const removing = useGesture((state) => state.removing);
  const lasso = useGesture((state) => state.lasso);
  const rectangle = useGesture((state) => state.rectangle);
  const radius = useSelectionOptions((options) => options.brushRadius);
  const dark = SCENE_COLORS.brushDark;
  const light = SCENE_COLORS.brushLight;
  const dash = removing ? '4 3' : undefined;

  return (
    <svg className={styles.drawing} aria-hidden data-testid="selection-drawing">
      {mode === 'select-brush' && pointer && (
        <g data-testid="brush-ring">
          <circle cx={pointer.x} cy={pointer.y} r={radius + 1} fill="none" stroke={dark} />
          <circle
            cx={pointer.x}
            cy={pointer.y}
            r={radius}
            fill="none"
            stroke={light}
            strokeDasharray={dash}
          />
        </g>
      )}
      {lasso && lasso.length >= 4 && (
        <>
          <polygon points={polygonPoints(lasso)} fill="none" stroke={dark} strokeWidth={3} />
          <polygon
            points={polygonPoints(lasso)}
            fill="none"
            stroke={light}
            strokeDasharray={dash}
          />
        </>
      )}
      {rectangle && (
        <>
          <rect
            x={Math.min(rectangle.from.x, rectangle.to.x)}
            y={Math.min(rectangle.from.y, rectangle.to.y)}
            width={Math.abs(rectangle.to.x - rectangle.from.x)}
            height={Math.abs(rectangle.to.y - rectangle.from.y)}
            fill="none"
            stroke={dark}
            strokeWidth={3}
          />
          <rect
            x={Math.min(rectangle.from.x, rectangle.to.x)}
            y={Math.min(rectangle.from.y, rectangle.to.y)}
            width={Math.abs(rectangle.to.x - rectangle.from.x)}
            height={Math.abs(rectangle.to.y - rectangle.from.y)}
            fill="none"
            stroke={light}
            strokeDasharray={dash}
          />
        </>
      )}
    </svg>
  );
}

function SelectionLayer() {
  const viewport = useViewport();
  const mode = useTools((state) => state.selectionMode);
  const anchor = useRef<HTMLDivElement>(null);
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const uninstall = installSelection();
    const stopLeaving = leaveModeWithoutScan();
    return () => {
      stopLeaving();
      uninstall();
    };
  }, []);

  useEffect(() => (viewport ? startViewportSync() : undefined), [viewport]);

  useEffect(() => {
    if (!viewport || !isSelectionModeId(mode)) return;
    return runSelectionMode(viewport, mode);
  }, [viewport, mode]);

  // The drawing covers the whole viewport, so it is placed in the viewport area
  // rather than in this overlay's corner.
  useLayoutEffect(() => {
    setHost(anchor.current?.closest('main') ?? null);
  }, []);

  useEffect(() => {
    if (!host) return;
    const leave = () => updateGesture({ pointer: null });
    host.addEventListener('pointerleave', leave);
    return () => host.removeEventListener('pointerleave', leave);
  }, [host]);

  return (
    <div ref={anchor}>
      <SelectionOptionsBar />
      {host && isSelectionModeId(mode) && createPortal(<GestureDrawing mode={mode} />, host)}
    </div>
  );
}

export const overlay: ViewportOverlay = {
  anchor: 'top-left',
  order: 20,
  Component: SelectionLayer,
};
