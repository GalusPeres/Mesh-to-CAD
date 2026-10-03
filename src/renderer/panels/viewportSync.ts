// Keeps the project tree and the viewport in step (docs/DESIGN.md 5.5): the object
// hovered or selected in the tree is highlighted in the viewport, and hovering or
// clicking a body or a fitted shape in the viewport selects its tree row.

import { useEffect } from 'react';

import type { RegionsPayload } from '@shared/protocol/generated/document-display';

import { kernel } from '../kernel/kernel';
import { documentStore } from '../state/documentStore';
import {
  hoverObject,
  type ObjectRef,
  objectSelectionStore,
  selectObjects,
} from '../state/objectSelectionStore';
import { toolStore } from '../state/toolStore';
import { type PickHit, useViewport, type Viewport } from '../viewport/api';
import { connectObjectVisibility } from './objectVisibility';
import { connectUsedConstruction } from './usedConstruction';

type HighlightTarget = { bodyId: string } | { owner: string } | null;

/** What the viewport highlights for an object: bodies by id, feature items by owner. */
export function highlightTarget(ref: ObjectRef | null): HighlightTarget {
  if (ref?.kind === 'body') return { bodyId: ref.id };
  if (ref?.kind === 'feature') return { owner: ref.id };
  return null;
}

/** The object a viewport hit belongs to. */
export function objectOfHit(hit: PickHit | null): ObjectRef | null {
  switch (hit?.kind) {
    case 'body':
    case 'edge':
      return { kind: 'body', id: hit.bodyId };
    case 'item':
      return { kind: 'feature', id: hit.owner };
    case 'scan':
      return { kind: 'scan', id: 'scan' };
    default:
      return null;
  }
}

/** Faces carrying one region label, for the hover tint of a region row. */
export function facesWithLabel(labels: Uint16Array, label: number): Uint32Array {
  let count = 0;
  for (const value of labels) if (value === label) count += 1;
  const faces = new Uint32Array(count);
  let next = 0;
  labels.forEach((value, face) => {
    if (value === label) faces[next++] = face;
  });
  return faces;
}

let labelCache: { key: string; labels: Promise<Uint16Array | null> } | null = null;

/** Region labels of the current scan, fetched once per regions payload key. */
function regionLabels(key: string): Promise<Uint16Array | null> {
  if (labelCache?.key !== key) {
    const labels = kernel()
      .call('scene.fetch', { keys: [key] })
      .result.then(({ payloads }) => {
        const payload = payloads.find((item): item is RegionsPayload => item.type === 'regions');
        return payload?.labels ?? null;
      })
      .catch(() => null);
    labelCache = { key, labels };
  }
  return labelCache.labels;
}

function syncHighlight(viewport: Viewport): () => void {
  let regionHover = false;
  let token = 0;
  const apply = () => {
    const { hovered, selected } = objectSelectionStore.getState();
    const target = hovered ?? selected[0] ?? null;
    viewport.highlight(highlightTarget(target));
    const current = ++token;
    const snapshot = documentStore.getState().snapshot;
    const region =
      target?.kind === 'region'
        ? snapshot?.document.regions.items.find((item) => item.id === target.id)
        : undefined;
    const regionsKey = snapshot?.scene.regions;
    if (region && regionsKey) {
      void regionLabels(regionsKey).then((labels) => {
        if (current !== token || !labels) return;
        viewport.scan.setHover(facesWithLabel(labels, region.label));
        regionHover = true;
      });
    } else if (regionHover) {
      // Only clear a hover this module set; the smart select preview uses it too.
      viewport.scan.setHover(null);
      regionHover = false;
    }
  };
  apply();
  const unsubscribeSelection = objectSelectionStore.subscribe(apply);
  const unsubscribeDocument = documentStore.subscribe((state, previous) => {
    if (state.snapshot?.scene.regions !== previous.snapshot?.scene.regions) apply();
  });
  return () => {
    unsubscribeSelection();
    unsubscribeDocument();
  };
}

/**
 * Hover and click picking of objects. The interaction never consumes events, so
 * navigation, selection modes and tool handles keep working; it is registered
 * first and therefore asked last.
 */
function syncPicking(viewport: Viewport): () => void {
  let frame = 0;
  let lastMove: { x: number; y: number } | null = null;
  const pickHover = () => {
    frame = 0;
    if (!lastMove) return;
    hoverObject(objectOfHit(viewport.pick(lastMove, { kinds: ['body', 'edge', 'item'] })));
  };
  const remove = viewport.addInteraction({
    onPointerMove(event) {
      if (event.buttons !== 0) return false;
      lastMove = event.screen;
      frame ||= requestAnimationFrame(pickHover);
      return false;
    },
    onPointerDown(event) {
      const { selectionMode, activeToolId } = toolStore.getState();
      if (event.button !== 0 || selectionMode || activeToolId) return false;
      const ref = objectOfHit(viewport.pick(event.screen));
      selectObjects(ref ? [ref] : []);
      return false;
    },
  });
  return () => {
    cancelAnimationFrame(frame);
    remove();
    hoverObject(null);
  };
}

/** Mounted once by the project tree. */
export function useViewportSync(): void {
  const viewport = useViewport();
  useEffect(() => {
    if (!viewport) return;
    const cleanups = [
      syncHighlight(viewport),
      syncPicking(viewport),
      connectObjectVisibility(viewport),
      connectUsedConstruction(),
    ];
    return () => cleanups.forEach((cleanup) => cleanup());
  }, [viewport]);
}
