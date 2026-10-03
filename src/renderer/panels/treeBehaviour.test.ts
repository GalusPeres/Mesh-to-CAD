import type { TFunction } from 'i18next';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { createFormatter } from '../i18n/format';
import { setDocumentSnapshot } from '../state/documentStore';
import { toolStore } from '../state/toolStore';
import { viewStore } from '../state/viewStore';
import { registerViewport, type Viewport } from '../viewport/api';
import { body, fit, makeDocument, makeSnapshot, testTranslator } from './fixtures';
import {
  canHide,
  EMPTY_HIDDEN,
  isHidden,
  isolate,
  isolation,
  objectVisibilityStore,
  showAll,
  somethingHidden,
  toggleHidden,
} from './objectVisibility';
import { treeMenuActions } from './treeMenu';
import type { ProjectNode } from './treeModel';
import { facesWithLabel, highlightTarget, objectOfHit } from './viewportSync';

const calls: { method: string; params: unknown }[] = [];
const responses = new Map<string, unknown>();

vi.mock('../kernel/kernel', () => ({
  kernel: () => ({
    call: (method: string, params: unknown) => {
      calls.push({ method, params });
      return { result: Promise.resolve(responses.get(method) ?? {}) };
    },
  }),
}));

const { dependentsQuestion, renameFeature, requestDelete, toggleSuppressed, treeDialogStore } =
  await import('./treeActions');

let t: TFunction;

beforeAll(async () => {
  t = await testTranslator('de');
});

function node(partial: Partial<ProjectNode>): ProjectNode {
  return { id: 'x', label: 'X', state: 'ok', ref: null, testId: 'tree-node-x', ...partial };
}

const snapshot = makeSnapshot(makeDocument([fit('f1', 'plane'), fit('f2', 'cylinder')]), {
  features: {},
  bodies: [body('f1'), body('f2')],
});

describe('treeMenuActions', () => {
  const visible = { hidden: false, canHide: true, anythingHidden: false };

  it('offers every entry for a feature, grouped as in the design', () => {
    const feature = node({
      ref: { kind: 'feature', id: 'f1' },
      edit: { toolId: 'fit-primitive', target: 'f1' },
    });
    expect(treeMenuActions(feature, visible)).toEqual([
      ['edit', 'rename'],
      ['hide', 'isolate'],
      ['suppress'],
      ['delete'],
    ]);
    expect(
      treeMenuActions(
        { ...feature, state: 'suppressed' },
        { ...visible, hidden: true, anythingHidden: true },
      ),
    ).toEqual([['edit', 'rename'], ['show', 'isolate', 'showAll'], ['unsuppress'], ['delete']]);
  });

  it('offers only what applies to other rows', () => {
    expect(treeMenuActions(node({ ref: { kind: 'scan', id: 'scan' } }), visible)).toEqual([
      ['hide', 'isolate'],
    ]);
    const alignment = node({ edit: { toolId: 'align-auto', target: 'alignment' } });
    expect(treeMenuActions(alignment, visible)).toEqual([['edit']]);
    const regionRow = node({ ref: { kind: 'region', id: 'r1' } });
    expect(treeMenuActions(regionRow, { ...visible, canHide: false })).toEqual([]);
    const featureWithoutHiding = node({ ref: { kind: 'feature', id: 'f1' } });
    expect(treeMenuActions(featureWithoutHiding, { ...visible, canHide: false })).toEqual([
      ['rename'],
      ['suppress'],
      ['delete'],
    ]);
  });
});

describe('object visibility', () => {
  const setHiddenObjects = vi.fn();

  beforeEach(() => {
    showAll();
    registerViewport(null);
    setHiddenObjects.mockReset();
  });

  afterEach(() => registerViewport(null));

  it('hides the scan through the view visibility, which Space also cycles', () => {
    const scan = { kind: 'scan', id: 'scan' } as const;
    expect(canHide(scan)).toBe(true);
    toggleHidden(scan, snapshot);
    expect(viewStore.getState().visibility).toBe('bodies');
    expect(isHidden(scan, EMPTY_HIDDEN, 'bodies')).toBe(true);
    toggleHidden(scan, snapshot);
    expect(viewStore.getState().visibility).toBe('both');
    viewStore.setState({ visibility: 'scan' });
    toggleHidden(scan, snapshot);
    expect(viewStore.getState().visibility).toBe('scan');
  });

  it('hides single bodies and features, not regions', () => {
    const ref = { kind: 'body', id: 'f1' } as const;
    expect(canHide(ref)).toBe(true);
    expect(canHide({ kind: 'region', id: 'r1' })).toBe(false);
    toggleHidden(ref, snapshot);
    expect(objectVisibilityStore.getState()).toEqual({ bodies: ['f1'], owners: [] });
    toggleHidden({ kind: 'feature', id: 'f2' }, snapshot);
    expect(objectVisibilityStore.getState()).toEqual({ bodies: ['f1'], owners: ['f2'] });
    toggleHidden(ref, snapshot);
    expect(objectVisibilityStore.getState()).toEqual({ bodies: [], owners: ['f2'] });
    expect(somethingHidden(objectVisibilityStore.getState(), 'both')).toBe(true);
  });

  it('isolates one object and shows everything again', () => {
    registerViewport({ setHiddenObjects } as unknown as Viewport);
    expect(isolation({ kind: 'body', id: 'f2' }, snapshot)).toEqual({
      hidden: { bodies: ['f1'], owners: ['f1', 'f2'] },
      visibility: 'bodies',
    });
    expect(isolation({ kind: 'feature', id: 'f1' }, snapshot).hidden).toEqual({
      bodies: ['f1', 'f2'],
      owners: ['f2'],
    });
    isolate({ kind: 'scan', id: 'scan' }, snapshot);
    expect(viewStore.getState().visibility).toBe('scan');
    isolate({ kind: 'body', id: 'f2' }, snapshot);
    expect(viewStore.getState().visibility).toBe('bodies');
    expect(isHidden({ kind: 'body', id: 'f1' }, objectVisibilityStore.getState(), 'bodies')).toBe(
      true,
    );
    showAll();
    expect(viewStore.getState().visibility).toBe('both');
    expect(somethingHidden(objectVisibilityStore.getState(), 'both')).toBe(false);
  });

  it('shows only the chosen object when all items were switched off', () => {
    registerViewport({ setHiddenObjects } as unknown as Viewport);
    viewStore.setState({ visibility: 'scan' });
    expect(isHidden({ kind: 'body', id: 'f1' }, EMPTY_HIDDEN, 'scan')).toBe(true);
    toggleHidden({ kind: 'body', id: 'f1' }, snapshot);
    expect(viewStore.getState().visibility).toBe('both');
    expect(objectVisibilityStore.getState()).toEqual({ bodies: ['f2'], owners: ['f1', 'f2'] });
  });
});

describe('viewport sync', () => {
  it('maps objects to highlight targets and viewport hits to objects', () => {
    expect(highlightTarget({ kind: 'body', id: 'f5' })).toEqual({ bodyId: 'f5' });
    expect(highlightTarget({ kind: 'feature', id: 'f3' })).toEqual({ owner: 'f3' });
    expect(highlightTarget({ kind: 'region', id: 'r1' })).toBeNull();
    const point = [0, 0, 0] as const;
    expect(objectOfHit({ kind: 'edge', bodyId: 'f5', edge: 2, point })).toEqual({
      kind: 'body',
      id: 'f5',
    });
    expect(objectOfHit({ kind: 'item', key: 'k', owner: 'f3', point })).toEqual({
      kind: 'feature',
      id: 'f3',
    });
    expect(objectOfHit({ kind: 'scan', face: 4, point })).toEqual({ kind: 'scan', id: 'scan' });
    expect(objectOfHit(null)).toBeNull();
  });

  it('finds the faces of a region label', () => {
    const labels = Uint16Array.from([0, 3, 3, 1, 3, 0]);
    expect([...facesWithLabel(labels, 3)]).toEqual([1, 2, 4]);
    expect(facesWithLabel(labels, 9)).toHaveLength(0);
  });
});

describe('tree actions', () => {
  beforeEach(() => {
    calls.length = 0;
    responses.clear();
    toolStore.setState({ activeToolId: null });
    treeDialogStore.setState({ rename: null, remove: null });
    setDocumentSnapshot(snapshot);
  });

  it('deletes at once when nothing depends on the feature', async () => {
    responses.set('doc.dependents', { featureIds: ['f2'] });
    await requestDelete('f2');
    expect(calls.map((call) => call.method)).toEqual(['doc.dependents', 'doc.apply']);
    expect(calls[1]?.params).toMatchObject({
      baseRevision: 3,
      ops: [{ type: 'deleteFeature', id: 'f2', cascade: false }],
    });
  });

  it('asks before deleting a feature that others use, naming them', async () => {
    responses.set('doc.dependents', { featureIds: ['f1', 'f2'] });
    await requestDelete('f1');
    expect(calls.map((call) => call.method)).toEqual(['doc.dependents']);
    expect(treeDialogStore.getState().remove).toEqual({ featureId: 'f1', dependents: ['f2'] });
    const names = new Map([
      ['f1', 'Skizze 1'],
      ['f2', 'Extrusion 1'],
      ['f3', 'Verrundung 1'],
    ]);
    expect(dependentsQuestion('f1', ['f2', 'f3'], names, createFormatter('de-DE'), t)).toBe(
      'Skizze 1 wird von Extrusion 1 und Verrundung 1 verwendet. Alle 3 löschen?',
    );
  });

  it('does not edit the document while a tool is open', async () => {
    toolStore.setState({ activeToolId: 'fit-primitive' });
    await requestDelete('f1');
    expect(await toggleSuppressed('f1')).toBe(false);
    expect(calls).toEqual([]);
  });

  it('suppresses and renames with one revision each; an empty name restores the default', async () => {
    await toggleSuppressed('f1');
    expect(calls[0]?.params).toMatchObject({
      ops: [{ type: 'setSuppressed', id: 'f1', suppressed: true }],
    });
    await renameFeature('f1', '  Grundfläche ');
    expect(calls[1]?.params).toMatchObject({
      ops: [{ type: 'renameFeature', id: 'f1', name: 'Grundfläche' }],
    });
    // Unchanged names create no revision.
    expect(await renameFeature('f1', '')).toBe(false);
    setDocumentSnapshot(makeSnapshot(makeDocument([fit('f1', 'plane', { name: 'Grundfläche' })])));
    await renameFeature('f1', '');
    expect(calls[2]?.params).toMatchObject({
      ops: [{ type: 'renameFeature', id: 'f1', name: null }],
    });
  });
});
