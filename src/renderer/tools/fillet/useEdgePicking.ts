import { useCallback, useEffect, useRef, useState } from 'react';
import { BufferGeometry, Float32BufferAttribute, LineBasicMaterial, LineSegments } from 'three';

import type { LinesPayload } from '@shared/protocol/generated/document-display';
import type { EdgeRef } from '@shared/protocol/generated/feature-fillet';

import { kernel } from '../../kernel/kernel';
import { documentStore } from '../../state/documentStore';
import { type PickHit, getViewport } from '../../viewport/api';
import { SCENE_COLORS } from '../../viewport/palette';
import { type EdgePayload, edgeForRef, edgeSegments } from './edges';

type EdgeHit = Extract<PickHit, { kind: 'edge' }>;

/** Loads the edge payload of a body (`bodyEdges` item of the current scene), cached by key. */
export function useEdgePayloads(): (bodyId: string) => Promise<EdgePayload | null> {
  const cache = useRef(new Map<string, Promise<EdgePayload | null>>());
  return useCallback((bodyId: string) => {
    const item = documentStore
      .getState()
      .snapshot?.scene.items.find(
        (entry) => entry.style === 'bodyEdges' && entry.bodyId === bodyId,
      );
    if (!item) return Promise.resolve(null);
    let pending = cache.current.get(item.key);
    if (!pending) {
      pending = kernel()
        .call('scene.fetch', { keys: [item.key] })
        .result.then(({ payloads }) => {
          const lines = payloads.find(
            (payload): payload is LinesPayload => payload.type === 'lines',
          );
          return lines ?? null;
        });
      cache.current.set(item.key, pending);
    }
    return pending;
  }, []);
}

/** The edge payload of one body, loaded when the body changes. */
export function useBodyEdgePayload(
  bodyId: string | null,
  load: (bodyId: string) => Promise<EdgePayload | null>,
): EdgePayload | null {
  const [loaded, setLoaded] = useState<{ bodyId: string; payload: EdgePayload | null } | null>(
    null,
  );
  useEffect(() => {
    if (!bodyId) return;
    let current = true;
    void load(bodyId).then((payload) => {
      if (current) setLoaded({ bodyId, payload });
    });
    return () => {
      current = false;
    };
  }, [bodyId, load]);
  return loaded && loaded.bodyId === bodyId ? loaded.payload : null;
}

/** Hover highlight and left-click picking of body edges while the tool is open. */
export function useEdgePickInteraction(onPick: (hit: EdgeHit) => void): void {
  const latest = useRef(onPick);
  useEffect(() => {
    latest.current = onPick;
  });
  useEffect(() => {
    const viewport = getViewport();
    if (!viewport) return;
    const pickEdge = (screen: { x: number; y: number }): EdgeHit | null => {
      const hit = viewport.pick(screen, { kinds: ['edge'] });
      return hit?.kind === 'edge' ? hit : null;
    };
    const remove = viewport.addInteraction({
      cursor: 'crosshair',
      onPointerMove: (event) => {
        const hit = pickEdge(event.screen);
        viewport.highlight(hit ? { bodyId: hit.bodyId, edge: hit.edge } : null);
        return false;
      },
      onPointerDown: (event) => {
        if (event.button !== 0) return false;
        const hit = pickEdge(event.screen);
        if (!hit) return false;
        latest.current(hit);
        return true;
      },
    });
    return () => {
      remove();
      viewport.highlight(null);
    };
  }, []);
}

/** Draws the chosen edges on top of the scene in the selection colour. */
export function useSelectedEdgesOverlay(
  payload: EdgePayload | null,
  faceTags: readonly string[] | null,
  edges: readonly EdgeRef[],
): void {
  useEffect(() => {
    const viewport = getViewport();
    if (!viewport || !payload || !faceTags || edges.length === 0) return;
    const ids = new Set<number>();
    for (const ref of edges) {
      const edge = edgeForRef(payload, faceTags, ref);
      if (edge !== null) ids.add(edge);
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new Float32BufferAttribute(edgeSegments(payload, ids), 3));
    const material = new LineBasicMaterial({ color: SCENE_COLORS.selection, depthTest: false });
    const lines = new LineSegments(geometry, material);
    lines.renderOrder = 10;
    const overlay = viewport.createOverlay();
    overlay.add(lines);
    viewport.invalidate();
    return () => {
      overlay.dispose();
      geometry.dispose();
      material.dispose();
      viewport.invalidate();
    };
  }, [payload, faceTags, edges]);
}
