import { describe, expect, it } from 'vitest';

import type { EdgeRef } from '@shared/protocol/generated/feature-fillet';

import { edgeDraftReducer, initialDraft } from './edgeDraft';

const edge = (tag: string): EdgeRef => ({ faces: [tag, 'f2:cap:end'], point: [0, 0, 0] });

describe('fillet edge draft', () => {
  it('adds, toggles off and removes edges', () => {
    let draft = initialDraft(null, []);
    draft = edgeDraftReducer(draft, { type: 'toggle', body: 'f2', ref: edge('a'), existing: null });
    draft = edgeDraftReducer(draft, { type: 'toggle', body: 'f2', ref: edge('b'), existing: null });
    expect(draft.body).toBe('f2');
    expect(draft.edges).toEqual([edge('a'), edge('b')]);
    draft = edgeDraftReducer(draft, { type: 'toggle', body: 'f2', ref: edge('a'), existing: 0 });
    expect(draft.edges).toEqual([edge('b')]);
    draft = edgeDraftReducer(draft, { type: 'remove', index: 0 });
    expect(draft.edges).toEqual([]);
    expect(draft.body).toBeNull();
  });

  it('undoes and redoes every change', () => {
    let draft = initialDraft('f2', [edge('a')]);
    draft = edgeDraftReducer(draft, { type: 'toggle', body: 'f2', ref: edge('b'), existing: null });
    draft = edgeDraftReducer(draft, { type: 'undo' });
    expect(draft.edges).toEqual([edge('a')]);
    draft = edgeDraftReducer(draft, { type: 'undo' });
    expect(draft.edges).toEqual([edge('a')]);
    draft = edgeDraftReducer(draft, { type: 'redo' });
    expect(draft.edges).toEqual([edge('a'), edge('b')]);
    expect(edgeDraftReducer(draft, { type: 'redo' })).toBe(draft);
  });

  it('drops the redo part after a new change', () => {
    let draft = initialDraft('f2', []);
    draft = edgeDraftReducer(draft, { type: 'toggle', body: 'f2', ref: edge('a'), existing: null });
    draft = edgeDraftReducer(draft, { type: 'undo' });
    draft = edgeDraftReducer(draft, { type: 'toggle', body: 'f2', ref: edge('c'), existing: null });
    expect(draft.future).toEqual([]);
    expect(draft.edges).toEqual([edge('c')]);
  });
});
