import { useEffect, useRef } from 'react';

import type { RecognizeResult } from '@shared/protocol/generated/recognize';

import { useFormatter } from '../../i18n/useFormatter';
import { getViewport } from '../../viewport/api';
import { groupLabels } from './model';
import { RecognitionOverlay } from './RecognitionOverlay';

interface Handlers {
  /** A label was clicked: check or uncheck its group. */
  onToggle: (group: number) => void;
  /** The pointer is over a label of this group (null: over none). */
  onHover: (group: number | null) => void;
}

/**
 * Draws the recognised features while the tool is open and lets the user hover and
 * click their labels in the viewport.
 */
export function useRecognitionOverlay(
  result: RecognizeResult | null,
  checked: ReadonlySet<number>,
  hovered: number | null,
  handlers: Handlers,
): void {
  const format = useFormatter();
  const overlayRef = useRef<RecognitionOverlay | null>(null);
  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    const viewport = getViewport();
    if (!viewport || !result) return;
    const texts = groupLabels(result, format);
    const overlay = new RecognitionOverlay(viewport.createOverlay(), result, texts);
    overlayRef.current = overlay;
    const groupOf = result.features.map((feature) => feature.group);
    const groupAt = (screen: { x: number; y: number }) => {
      const index = overlay.labelAt(screen, (point) => viewport.worldToScreen(point));
      return index === null ? null : (groupOf[index] ?? null);
    };
    let over: number | null = null;
    const removeInteraction = viewport.addInteraction({
      onPointerMove: (event) => {
        const group = groupAt(event.screen);
        if (group !== over) {
          over = group;
          handlersRef.current.onHover(group);
        }
        return false;
      },
      onPointerDown: (event) => {
        if (event.button !== 0) return false;
        const group = groupAt(event.screen);
        if (group === null) return false;
        handlersRef.current.onToggle(group);
        return true;
      },
    });
    viewport.invalidate();
    return () => {
      removeInteraction();
      overlay.dispose();
      overlayRef.current = null;
      viewport.invalidate();
    };
  }, [result, format]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !result) return;
    overlay.paint(
      result.features.map((feature) => feature.group),
      checked,
      hovered,
    );
    getViewport()?.invalidate();
  }, [result, checked, hovered, format]);
}
