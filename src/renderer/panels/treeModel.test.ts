import i18next, { type TFunction } from 'i18next';
import { beforeAll, describe, expect, it } from 'vitest';

import type { Document, Feature, Region } from '@shared/protocol/generated/document-model';
import type { DocumentStatus } from '@shared/protocol/generated/document-snapshot';

import { featureNames } from '../features/registry';
import { createFormatter } from '../i18n/format';
import { buildResources } from '../i18n/resources';
import { buildProjectTree, findNode, type ProjectNode, usedRegionIds } from './treeModel';

let t: TFunction;

beforeAll(async () => {
  const instance = i18next.createInstance();
  await instance.init({
    resources: buildResources(),
    lng: 'de',
    fallbackLng: 'de',
    defaultNS: 'common',
    interpolation: { escapeValue: false },
  });
  t = instance.t;
});

const blob = { id: 'b', byteLength: 0 } as never;

function region(id: string, label: number, kind: Region['kind'], rms: number | null = 0.02) {
  return { id, label, name: null, kind, rms, faceCount: 100, area: 10, colorIndex: label } as Region;
}

function fit(id: string, kind: string, extra: Partial<Feature> = {}, sourceRegion?: string): Feature {
  return {
    id,
    type: 'fit',
    name: null,
    suppressed: false,
    params: { kind, sourceRegion: sourceRegion ?? null },
    ...extra,
  };
}

function makeDocument(features: Feature[], regions: Region[] = []): Document {
  return {
    revision: 3,
    nextId: 10,
    scan: {
      key: 'k',
      source: { fileName: 'bracket.stl', sha256: 'x', importUnit: 'mm' },
      vertices: blob,
      faces: blob,
      synthetic: null,
      vertexCount: 600,
      faceCount: 1200,
      origin: [0, 0, 0],
      noise: 0.03,
      displaySmoothing: 0,
      operations: [
        { op: 'import', counts: {} },
        { op: 'repair', counts: {} },
      ],
    },
    alignment: {
      method: 'faces',
      params: null,
      adjust: { flipX: false, flipZ: false, rotateZ90: 0 },
      matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] as never,
    },
    regions: { labels: null, items: regions },
    features,
    settings: { tolerance: 0.1, snapUnits: 'metric', noiseOverride: null, deviationMaxDistance: 1 },
  } as Document;
}

function build(
  document: Document,
  status: DocumentStatus = { features: {}, bodies: [] },
  onlyUnusedRegions = false,
): ProjectNode[] {
  return buildProjectTree({
    document,
    status,
    t,
    format: createFormatter('de-DE'),
    featureNames: featureNames(document.features, t),
    editTools: new Map([['fit', 'fit-primitive']]),
    onlyUnusedRegions,
  });
}

describe('buildProjectTree', () => {
  it('is empty without a scan', () => {
    expect(build({ ...makeDocument([]), scan: null })).toEqual([]);
  });

  it('orders the groups and hides groups without content', () => {
    const nodes = build(makeDocument([]));
    expect(nodes.map((node) => node.id)).toEqual(['scan', 'origin', 'history']);
    expect(nodes[0]?.secondary).toBe('1.200 Dreiecke');
    // The import itself is not listed as a preparation step.
    expect(nodes[0]?.children?.map((node) => node.label)).toEqual(['Repariert']);
  });

  it('puts the alignment first in the history and opens the matching tool', () => {
    const nodes = build(makeDocument([fit('f1', 'cylinder')]));
    const history = findNode(nodes, 'history');
    expect(history?.children?.map((node) => node.id)).toEqual(['alignment', 'feature:f1']);
    expect(findNode(nodes, 'alignment')?.edit).toEqual({
      toolId: 'align-faces',
      target: 'alignment',
    });
    const auto = makeDocument([]);
    auto.alignment.method = 'auto';
    expect(findNode(build(auto), 'alignment')?.edit?.toolId).toBe('align-auto');
  });

  it('numbers default names per base name and keeps user names', () => {
    const nodes = build(
      makeDocument([
        fit('f1', 'cylinder'),
        fit('f2', 'plane'),
        fit('f3', 'cylinder', { name: 'Bohrung' }),
        fit('f4', 'cylinder'),
      ]),
    );
    const labels = findNode(nodes, 'history')?.children?.map((node) => node.label);
    expect(labels).toEqual(['Ausrichtung', 'Zylinder 1', 'Ebene 1', 'Bohrung', 'Zylinder 3']);
    expect(findNode(nodes, 'feature:f1')?.edit).toEqual({ toolId: 'fit-primitive', target: 'f1' });
  });

  it('shows feature states, with suppression taking precedence', () => {
    const status: DocumentStatus = {
      features: {
        f1: { state: 'warning', issues: [], error: null, stats: {} },
        f2: { state: 'ok', issues: [], error: null, stats: {} },
        f3: { state: 'skipped', issues: [], error: null, stats: {} },
      },
      bodies: [],
    };
    const nodes = build(
      makeDocument([fit('f1', 'plane'), fit('f2', 'plane', { suppressed: true }), fit('f3', 'plane')]),
      status,
    );
    expect(findNode(nodes, 'feature:f1')?.state).toBe('warning');
    expect(findNode(nodes, 'feature:f2')?.state).toBe('suppressed');
    expect(findNode(nodes, 'feature:f3')?.state).toBe('skipped');
  });

  it('groups regions by type in a fixed order and names them "Bereich N"', () => {
    const regions = [
      region('r3', 3, 'cylinder'),
      region('r1', 1, 'plane'),
      region('r2', 2, 'plane', null),
      region('r4', 4, 'unknown'),
    ];
    const nodes = build(makeDocument([], regions));
    const group = findNode(nodes, 'regions');
    expect(group?.label).toBe('Bereiche (4)');
    expect(group?.children?.map((node) => node.label)).toEqual([
      'Ebenen (2)',
      'Zylinder (1)',
      'Unbestimmt (1)',
    ]);
    const planes = findNode(nodes, 'regions:plane')?.children ?? [];
    expect(planes.map((node) => node.label)).toEqual(['Bereich 1', 'Bereich 2']);
    expect(planes[0]?.secondary).toBe('Ebene, RMS 0,020 mm');
    expect(planes[1]?.secondary).toBe('Ebene');
    expect(planes[0]?.ref).toEqual({ kind: 'region', id: 'r1' });
  });

  it('filters regions already used by a feature', () => {
    const regions = [region('r1', 1, 'plane'), region('r2', 2, 'cylinder')];
    const document = makeDocument([fit('f1', 'cylinder', {}, 'r2')], regions);
    expect([...usedRegionIds(document)]).toEqual(['r2']);
    const nodes = build(document, undefined, true);
    expect(findNode(nodes, 'region:r2')).toBeNull();
    expect(findNode(nodes, 'region:r1')).not.toBeNull();
    expect(findNode(nodes, 'regions')?.label).toBe('Bereiche (2)');
  });

  it('lists bodies with their validity', () => {
    const body = {
      owner: 'f1',
      solids: 1,
      volume: 1000,
      area: 600,
      maxTolerance: 1e-7,
      faceTags: [],
    };
    const nodes = build(makeDocument([]), {
      features: {},
      bodies: [
        { ...body, id: 'b1', valid: true },
        { ...body, id: 'b2', valid: false },
      ],
    });
    const bodies = findNode(nodes, 'bodies');
    expect(bodies?.label).toBe('Körper (2)');
    expect(bodies?.children?.map((node) => [node.label, node.state])).toEqual([
      ['Körper 1', 'ok'],
      ['Körper 2', 'error'],
    ]);
  });
});
