import { useEffect } from 'react';

import { getViewport } from '../viewport/api';
import { type ObjectRef, objectSelectionStore } from '../state/objectSelectionStore';

type HighlightTarget = { bodyId: string } | { owner: string } | null;

/** What the viewport highlights for an object: bodies by id, features by owner. */
export function highlightTarget(ref: ObjectRef | null): HighlightTarget {
  if (ref?.kind === 'body') return { bodyId: ref.id };
  if (ref?.kind === 'feature') return { owner: ref.id };
  return null;
}

/** Keep the viewport highlight on the hovered object, else on the selected one. */
export function useViewportHighlight(): void {
  useEffect(() => {
    const apply = () => {
      const { hovered, selected } = objectSelectionStore.getState();
      getViewport()?.highlight(highlightTarget(hovered ?? selected[0] ?? null));
    };
    apply();
    return objectSelectionStore.subscribe(apply);
  }, []);
}
