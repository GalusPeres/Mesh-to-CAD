import type { TFunction } from 'i18next';
import { Box } from 'lucide-react';
import { beforeAll, describe, expect, it } from 'vitest';

import type { Document } from '@shared/protocol/generated/document-model';
import type { DocumentStatus } from '@shared/protocol/generated/document-snapshot';

import { featureNames } from '../features/registry';
import type { FeatureView } from '../features/types';
import { createFormatter } from '../i18n/format';
import type { ToolDefinition } from '../tools/framework/types';
import { featureEditTools } from './editTools';
import { body, fit, makeDocument, region, testTranslator } from './fixtures';
import {
  buildProjectTree,
  DEFAULT_EXPANDED,
  findNode,
  nodeIdOf,
  operationLabel,
  type ProjectNode,
  usedRegionIds,
} from './treeModel';

let t: TFunction;
let tEnglish: TFunction;

beforeAll(async () => {
  t = await testTranslator('de');
  tEnglish = await testTranslator('en');
});

function build(
  document: Document,
  status: DocumentStatus = { features: {}, bodies: [] },
  options: { onlyUnusedRegions?: boolean; english?: boolean } = {},
): ProjectNode[] {
  const translate = options.english ? tEnglish : t;
  return buildProjectTree({
    document,
    status,
    t: translate,
    format: createFormatter(options.english ? 'en-US' : 'de-DE'),
    featureNames: featureNames(document.features, translate),
    editTools: new Map([['fit', 'fit-primitive']]),
    summaries: new Map([['f1', 'D 16,000 mm']]),
    onlyUnusedRegions: options.onlyUnusedRegions ?? false,
  });
}

describe('buildProjectTree', () => {
  it('is empty without a scan', () => {
    expect(build({ ...makeDocument(), scan: null })).toEqual([]);
  });

  it('orders the groups and hides groups without content', () => {
    const nodes = build(makeDocument());
    expect(nodes.map((node) => node.id)).toEqual(['scan', 'origin', 'history']);
    const withEverything = build(makeDocument([fit('f1', 'plane')], [region('r1', 1, 'plane')]), {
      features: {},
      bodies: [body('f1')],
    });
    expect(withEverything.map((node) => node.id)).toEqual([
      'scan',
      'regions',
      'bodies',
      'origin',
      'history',
    ]);
    // Bereiche stays collapsed by default; the other groups with content are open.
    expect(DEFAULT_EXPANDED).not.toContain('regions');
    expect(DEFAULT_EXPANDED).toEqual(expect.arrayContaining(['scan', 'bodies', 'history']));
  });

  it('shows the scan with file name, triangle count and its preparation steps', () => {
    const [scan] = build(makeDocument());
    expect(scan?.label).toBe('Scan');
    expect(scan?.secondary).toBe('bracket.stl · 1.200 Dreiecke');
    expect(scan?.ref).toEqual({ kind: 'scan', id: 'scan' });
    // The import itself is not listed as a preparation step.
    expect(scan?.children?.map((node) => node.label)).toEqual([
      'Repariert',
      'Reduziert auf 1.200 Dreiecke',
    ]);
    const [english] = build(makeDocument(), undefined, { english: true });
    expect(english?.secondary).toBe('bracket.stl · 1,200 triangles');
  });

  it('labels every preparation operation with its count', () => {
    const format = createFormatter('de-DE');
    const label = (op: string, counts: Record<string, number>) =>
      operationLabel({ op, counts }, t, format);
    expect(label('removeSmallParts', { removedParts: 1, removedFaces: 20 })).toBe(
      '1 kleines Teil entfernt',
    );
    expect(label('removeSmallParts', { removedParts: 12 })).toBe('12 kleine Teile entfernt');
    expect(label('fillHoles', { filledHoles: 3, openHoles: 1 })).toBe('3 Löcher gefüllt');
    expect(label('deleteFaces', { deletedFaces: 12408 })).toBe('12.408 Dreiecke gelöscht');
    expect(label('decimate', { facesAfter: 1_000_000 })).toBe('Reduziert auf 1.000.000 Dreiecke');
    expect(label('somethingNew', {})).toBe('Bearbeitet');
  });

  it('puts the alignment first in the history and opens the matching tool', () => {
    const nodes = build(makeDocument([fit('f1', 'cylinder')]));
    const history = findNode(nodes, 'history');
    expect(history?.children?.map((node) => node.id)).toEqual(['alignment', 'feature:f1']);
    expect(findNode(nodes, 'alignment')?.edit).toEqual({
      toolId: 'align-faces',
      target: 'alignment',
    });
    expect(findNode(nodes, 'alignment')?.secondary).toBe('An Flächen');
    const auto = makeDocument();
    auto.alignment.method = 'auto';
    expect(findNode(build(auto), 'alignment')?.edit?.toolId).toBe('align-auto');
    const none = makeDocument();
    none.alignment.method = 'none';
    expect(findNode(build(none), 'alignment')?.edit).toEqual({
      toolId: 'align-auto',
      target: 'alignment',
    });
  });

  it('numbers default names per base name and keeps user names', () => {
    const nodes = build(
      makeDocument([
        fit('f1', 'cylinder'),
        fit('f2', 'plane'),
        fit('f3', 'cylinder', { name: 'Bohrung' }),
        fit('f4', 'cylinder'),
        fit('f5', 'plane'),
      ]),
    );
    const labels = findNode(nodes, 'history')?.children?.map((node) => node.label);
    expect(labels).toEqual([
      'Ausrichtung',
      'Zylinder 1',
      'Ebene 1',
      'Bohrung',
      'Zylinder 3',
      'Ebene 2',
    ]);
    expect(findNode(nodes, 'feature:f1')?.edit).toEqual({ toolId: 'fit-primitive', target: 'f1' });
    expect(findNode(nodes, 'feature:f1')?.secondary).toBe('D 16,000 mm');
    expect(findNode(nodes, 'feature:f1')?.testId).toBe('tree-node-f1');
    // A renamed item keeps its name in every language.
    const english = build(
      makeDocument([fit('f1', 'cylinder'), fit('f3', 'cylinder', { name: 'Bohrung' })]),
      undefined,
      { english: true },
    );
    expect(findNode(english, 'history')?.children?.map((node) => node.label)).toEqual([
      'Alignment',
      'Cylinder 1',
      'Bohrung',
    ]);
  });

  it('shows feature states, with suppression taking precedence', () => {
    const state = (value: 'ok' | 'warning' | 'error' | 'skipped') => ({
      state: value,
      issues: [],
      error: null,
      stats: {},
    });
    const nodes = build(
      makeDocument([
        fit('f1', 'plane'),
        fit('f2', 'plane', { suppressed: true }),
        fit('f3', 'plane'),
        fit('f4', 'plane'),
        fit('f5', 'plane'),
      ]),
      {
        features: {
          f1: state('warning'),
          f2: state('ok'),
          f3: state('skipped'),
          f4: state('error'),
        },
        bodies: [],
      },
    );
    const states = ['f1', 'f2', 'f3', 'f4', 'f5'].map(
      (id) => findNode(nodes, `feature:${id}`)?.state,
    );
    expect(states).toEqual(['warning', 'suppressed', 'skipped', 'error', 'ok']);
  });

  it('groups regions by type in a fixed order and names them "Bereich N"', () => {
    const regions = [
      region('r3', 3, 'cylinder'),
      region('r1', 7, 'plane'),
      region('r2', 2, 'plane', null),
      region('r4', 4, 'unknown'),
      region('r5', 5, 'torus'),
    ];
    const nodes = build(makeDocument([], regions));
    const group = findNode(nodes, 'regions');
    expect(group?.label).toBe('Bereiche (5)');
    expect(group?.children?.map((node) => node.label)).toEqual([
      'Ebenen (2)',
      'Zylinder (1)',
      'Tori (1)',
      'Unbestimmt (1)',
    ]);
    const planes = findNode(nodes, 'regions:plane')?.children ?? [];
    // Sorted by label; the type is the icon and the secondary text, never the name.
    expect(planes.map((node) => node.label)).toEqual(['Bereich 2', 'Bereich 7']);
    expect(planes.map((node) => node.secondary)).toEqual(['Ebene', 'Ebene, RMS 0,020 mm']);
    expect(planes.map((node) => node.icon)).toEqual(['region:plane', 'region:plane']);
    expect(planes[1]?.ref).toEqual({ kind: 'region', id: 'r1' });
    expect(planes[1]?.testId).toBe('tree-node-r1');
  });

  it('filters regions already used by a feature', () => {
    const regions = [region('r1', 1, 'plane'), region('r2', 2, 'cylinder')];
    const document = makeDocument([fit('f1', 'cylinder', {}, 'r2')], regions);
    expect([...usedRegionIds(document)]).toEqual(['r2']);
    const nodes = build(document, undefined, { onlyUnusedRegions: true });
    expect(findNode(nodes, 'region:r2')).toBeNull();
    expect(findNode(nodes, 'regions:cylinder')).toBeNull();
    expect(findNode(nodes, 'region:r1')).not.toBeNull();
    // The group still counts every region.
    expect(findNode(nodes, 'regions')?.label).toBe('Bereiche (2)');
    expect(findNode(build(document), 'region:r2')).not.toBeNull();
  });

  it('lists bodies with their validity and the feature that last changed them', () => {
    const nodes = build(makeDocument([fit('f1', 'plane'), fit('f2', 'plane')]), {
      features: {},
      bodies: [body('f1', { owner: 'f2' }), body('f7', { valid: false })],
    });
    const bodies = findNode(nodes, 'bodies');
    expect(bodies?.label).toBe('Körper (2)');
    expect(bodies?.children?.map((node) => [node.label, node.state, node.secondary])).toEqual([
      ['Körper 1', 'ok', 'Ebene 2'],
      ['Körper 2', 'error', undefined],
    ]);
    // Body ids equal feature ids, so their test ids carry a prefix.
    expect(bodies?.children?.map((node) => node.testId)).toEqual([
      'tree-node-body-f1',
      'tree-node-body-f7',
    ]);
    expect(nodeIdOf({ kind: 'body', id: 'f1' })).toBe('body:f1');
    expect(findNode(nodes, nodeIdOf({ kind: 'body', id: 'f1' }))?.ref).toEqual({
      kind: 'body',
      id: 'f1',
    });
  });

  it('lists the origin planes and axes', () => {
    const origin = findNode(build(makeDocument()), 'origin');
    expect(origin?.children?.map((node) => node.label)).toEqual(['XY', 'YZ', 'XZ', 'Achsen']);
  });
});

describe('featureEditTools', () => {
  const tool = (id: string, edits: string[]) => ({ id, edits }) as unknown as ToolDefinition;
  const view = (type: string, editTool?: string) =>
    ({ type, icon: Box, editTool }) as unknown as FeatureView;

  it('prefers the feature view and falls back to the tool that declares the type', () => {
    const tools = featureEditTools(
      [view('fit', 'fit-primitive'), view('loft')],
      [tool('other-fit', ['fit']), tool('loft', ['loft']), tool('second-loft', ['loft'])],
    );
    expect(tools.get('fit')).toBe('fit-primitive');
    expect(tools.get('loft')).toBe('loft');
    expect(tools.has('sketch')).toBe(false);
  });
});
