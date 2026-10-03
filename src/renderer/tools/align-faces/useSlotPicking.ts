import { useCallback, useEffect, useRef } from 'react';

import type { RegionsPayload } from '@shared/protocol/generated/document-display';
import type { Document } from '@shared/protocol/generated/document-model';

import { kernel } from '../../kernel/kernel';
import { documentStore } from '../../state/documentStore';
import { type ObjectRef, objectSelectionStore, sameObject } from '../../state/objectSelectionStore';
import { toolStore } from '../../state/toolStore';
import { useViewport } from '../../viewport/api';
import { type SlotInput, inputFromObject } from './slots';

/** Region labels per scan face, loaded on the first scan pick and kept per payload key. */
function useRegionLabels(): (key: string) => Promise<Uint16Array | null> {
  const cache = useRef<{ key: string; labels: Uint16Array } | null>(null);
  return useCallback(async (key: string) => {
    if (cache.current?.key === key) return cache.current.labels;
    const { payloads } = await kernel().call('scene.fetch', { keys: [key] }).result;
    const payload = payloads.find((item): item is RegionsPayload => item.type === 'regions');
    if (!payload) return null;
    cache.current = { key, labels: payload.labels };
    return payload.labels;
  }, []);
}

function regionAt(document: Document, labels: Uint16Array, face: number): ObjectRef | null {
  const label = labels[face] ?? 0;
  const region = label ? document.regions.items.find((item) => item.label === label) : undefined;
  return region ? { kind: 'region', id: region.id } : null;
}

/**
 * Inputs picked in the project tree or in the viewport go to the active slot.
 * In the viewport a click on a fitted shape or reference geometry picks that feature,
 * a click on the scan picks the region under the cursor. While a selection mode
 * (brush, lasso, ...) is active, clicks belong to it and are not used here.
 */
export function useSlotPicking(onPick: (input: SlotInput) => void): void {
  const latest = useRef(onPick);
  useEffect(() => {
    latest.current = onPick;
  });
  const regionLabels = useRegionLabels();
  const viewport = useViewport();

  useEffect(
    () =>
      objectSelectionStore.subscribe((state, previous) => {
        const picked = state.selected.at(-1);
        if (!picked || previous.selected.some((item) => sameObject(item, picked))) return;
        const document = documentStore.getState().snapshot?.document;
        const input = document ? inputFromObject(picked, document) : null;
        if (input) latest.current(input);
      }),
    [],
  );

  useEffect(() => {
    if (!viewport) return;
    return viewport.addInteraction({
      onPointerDown: (event) => {
        if (event.button !== 0 || event.ctrl || event.shift || event.alt) return false;
        if (toolStore.getState().selectionMode !== null) return false;
        const snapshot = documentStore.getState().snapshot;
        const hit = viewport.pick(event.screen, { kinds: ['item', 'scan'] });
        if (!snapshot || !hit) return false;
        if (hit.kind === 'item') {
          const input = inputFromObject({ kind: 'feature', id: hit.owner }, snapshot.document);
          if (!input) return false;
          latest.current(input);
          return true;
        }
        const regionsKey = snapshot.scene.regions;
        if (hit.kind !== 'scan' || !regionsKey) return false;
        void regionLabels(regionsKey).then((labels) => {
          const document = documentStore.getState().snapshot?.document;
          const region = labels && document ? regionAt(document, labels, hit.face) : null;
          const input = region && document ? inputFromObject(region, document) : null;
          if (input) latest.current(input);
        });
        return true;
      },
    });
  }, [viewport, regionLabels]);
}
