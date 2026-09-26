import { useCallback, useEffect, useRef, useState } from 'react';

import { setDraftHistoryHandler } from '../../state/historyStore';
import { setDraftDirty } from '../../state/toolStore';

interface History<T> {
  past: T[];
  present: T;
  future: T[];
}

/**
 * A tool draft with its own undo history: while the tool is open, Ctrl+Z steps back
 * through draft changes and never reaches committed revisions (docs/DESIGN.md 5.1).
 * Any change marks the draft dirty, so switching tools asks before discarding it.
 */
export function useUndoableDraft<T>(initial: () => T): [T, (update: (value: T) => T) => void] {
  const [history, setHistory] = useState<History<T>>(() => ({
    past: [],
    present: initial(),
    future: [],
  }));
  const latest = useRef(history);
  useEffect(() => {
    latest.current = history;
  });

  const update = useCallback((change: (value: T) => T) => {
    setHistory((state) => {
      const next = change(state.present);
      if (Object.is(next, state.present)) return state;
      return { past: [...state.past, state.present], present: next, future: [] };
    });
    setDraftDirty(true);
  }, []);

  useEffect(() => {
    setDraftHistoryHandler({
      undo: () => {
        const { past, present, future } = latest.current;
        const previous = past.at(-1);
        if (previous === undefined) return false;
        setHistory({ past: past.slice(0, -1), present: previous, future: [present, ...future] });
        return true;
      },
      redo: () => {
        const { past, present, future } = latest.current;
        const [next, ...rest] = future;
        if (next === undefined) return false;
        setHistory({ past: [...past, present], present: next, future: rest });
        return true;
      },
    });
    return () => setDraftHistoryHandler(null);
  }, []);

  return [history.present, update];
}
