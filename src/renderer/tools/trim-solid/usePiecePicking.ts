import { useEffect, useRef } from 'react';

import type { PieceChoice } from '@shared/protocol/generated/feature-trim-solid';

import { type PickHit, getViewport } from '../../viewport/api';
import { setTrimHint } from './trimSession';

/** Whose preview the clicks act on: the trim's result body and its feature (ghosts). */
export interface PieceTargets {
  /** Body the trim produces (kept pieces); a click on it removes that piece. */
  body: string | null;
  /** The previewed trim feature; a click on one of its ghosts keeps that piece. */
  feature: string | null;
}

/**
 * Clicks on the trim's preview while the tool is open: a kept piece (the result body)
 * is removed, a removed one (its ghost) kept again. The click point names the piece.
 */
export function usePiecePicking(
  targets: PieceTargets,
  onChoice: (choice: PieceChoice) => void,
): void {
  const latest = useRef({ targets, onChoice });
  useEffect(() => {
    latest.current = { targets, onChoice };
  });
  useEffect(() => {
    const viewport = getViewport();
    if (!viewport) return;
    // The nearest hit first; a coplanar plane or the input net in front of the result
    // must not swallow the click, so then the body and the ghosts are asked alone.
    const choiceAt = (screen: { x: number; y: number }): PieceChoice | null => {
      const { body, feature } = latest.current.targets;
      const own = (hit: PickHit | null): PieceChoice | null => {
        if (hit?.kind === 'body' && body && hit.bodyId === body)
          return { point: [...hit.point], keep: false };
        if (hit?.kind === 'item' && feature && hit.owner === feature)
          return { point: [...hit.point], keep: true };
        return null;
      };
      return (
        own(viewport.pick(screen, { kinds: ['body', 'item'] })) ??
        own(viewport.pick(screen, { kinds: ['body'] })) ??
        own(viewport.pick(screen, { kinds: ['item'] }))
      );
    };
    setTrimHint('pick');
    const remove = viewport.addInteraction({
      cursor: 'pointer',
      onPointerMove: (event) => {
        const choice = choiceAt(event.screen);
        setTrimHint(choice ? (choice.keep ? 'keep' : 'remove') : 'pick');
        return false;
      },
      onPointerDown: (event) => {
        if (event.button !== 0) return false;
        const choice = choiceAt(event.screen);
        if (!choice) return false;
        latest.current.onChoice(choice);
        return true;
      },
    });
    return () => {
      remove();
      setTrimHint(null);
    };
  }, []);
}
