// The fillet tool's draft: picked edges with undo and redo inside the open tool
// (docs/DESIGN.md 5.1: Ctrl+Z undoes draft changes before any committed revision).

import type { EdgeRef } from '@shared/protocol/generated/feature-fillet';

export interface EdgeDraft {
  body: string | null;
  edges: EdgeRef[];
  past: { body: string | null; edges: EdgeRef[] }[];
  future: { body: string | null; edges: EdgeRef[] }[];
}

export type EdgeDraftAction =
  | { type: 'toggle'; body: string; ref: EdgeRef; existing: number | null }
  | { type: 'remove'; index: number }
  | { type: 'undo' }
  | { type: 'redo' };

export function initialDraft(body: string | null, edges: EdgeRef[]): EdgeDraft {
  return { body, edges, past: [], future: [] };
}

function change(draft: EdgeDraft, body: string | null, edges: EdgeRef[]): EdgeDraft {
  return {
    body: edges.length ? body : null,
    edges,
    past: [...draft.past, { body: draft.body, edges: draft.edges }],
    future: [],
  };
}

/**
 * `toggle` adds a picked edge, or removes it when it is already chosen (`existing` is
 * its index). Edges of another body than the chosen one are ignored by the caller.
 */
export function edgeDraftReducer(draft: EdgeDraft, action: EdgeDraftAction): EdgeDraft {
  switch (action.type) {
    case 'toggle':
      return action.existing === null
        ? change(draft, action.body, [...draft.edges, action.ref])
        : change(
            draft,
            action.body,
            draft.edges.filter((_edge, index) => index !== action.existing),
          );
    case 'remove':
      return change(
        draft,
        draft.body,
        draft.edges.filter((_edge, index) => index !== action.index),
      );
    case 'undo': {
      const previous = draft.past.at(-1);
      if (!previous) return draft;
      return {
        ...previous,
        past: draft.past.slice(0, -1),
        future: [{ body: draft.body, edges: draft.edges }, ...draft.future],
      };
    }
    case 'redo': {
      const next = draft.future[0];
      if (!next) return draft;
      return {
        ...next,
        past: [...draft.past, { body: draft.body, edges: draft.edges }],
        future: draft.future.slice(1),
      };
    }
  }
}
