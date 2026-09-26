// Pure model of the project tree (docs/DESIGN.md 5.5): which groups exist, their
// order, default names and the region grouping. The React component only adds
// icons for states and wires the events.

import type { TFunction } from 'i18next';

import type { Document, Region, RegionKind } from '@shared/protocol/generated/document-model';
import type { DocumentStatus } from '@shared/protocol/generated/document-snapshot';
import type { FeatureState } from '@shared/protocol/generated/document-results';

import type { Formatter } from '../i18n/format';
import type { ObjectRef } from '../state/objectSelectionStore';

export type ProjectNodeIcon =
  | 'scan'
  | 'operation'
  | 'regions'
  | 'bodies'
  | 'body'
  | 'origin'
  | 'plane'
  | 'axes'
  | 'history'
  | 'alignment'
  | `region:${RegionKind}`
  | `feature:${string}`;

export interface ProjectNode {
  id: string;
  label: string;
  secondary?: string;
  icon?: ProjectNodeIcon;
  /** Feature state; `ok` for everything that is not a feature. */
  state: FeatureState;
  /** The object this row stands for; groups have none. */
  ref: ObjectRef | null;
  /** Tool opened by double-click or Enter, with its edit target. */
  edit?: { toolId: string; target: string };
  children?: ProjectNode[];
  testId: string;
}

export interface TreeModelInput {
  document: Document;
  status: DocumentStatus;
  t: TFunction;
  format: Formatter;
  /** Display names from `featureNames` (renamed or type plus ordinal). */
  featureNames: ReadonlyMap<string, string>;
  /** Feature type to edit tool id (`FeatureView.editTool`). */
  editTools: ReadonlyMap<string, string>;
  summaries?: ReadonlyMap<string, string>;
  onlyUnusedRegions: boolean;
}

/** Order of the region type groups: analytic types first, freeform and unknown last. */
export const REGION_KIND_ORDER: readonly RegionKind[] = [
  'plane',
  'cylinder',
  'cone',
  'sphere',
  'torus',
  'freeform',
  'unknown',
];

/** Regions referenced by a feature (`params.sourceRegion`). */
export function usedRegionIds(document: Document): Set<string> {
  const used = new Set<string>();
  for (const feature of document.features) {
    const params = feature.params;
    if (params && typeof params === 'object' && !Array.isArray(params)) {
      const source = params.sourceRegion;
      if (typeof source === 'string') used.add(source);
    }
  }
  return used;
}

export function regionName(region: Region, t: TFunction): string {
  return region.name ?? t('panels:tree.region', { number: region.label });
}

function regionNodes(input: TreeModelInput): ProjectNode | null {
  const { document, t, format } = input;
  const items = document.regions.items;
  if (!items.length) return null;
  const used = input.onlyUnusedRegions ? usedRegionIds(document) : new Set<string>();
  const visible = items.filter((region) => !used.has(region.id));
  const groups: ProjectNode[] = [];
  for (const kind of REGION_KIND_ORDER) {
    const regions = visible
      .filter((region) => region.kind === kind)
      .sort((a, b) => a.label - b.label);
    if (!regions.length) continue;
    groups.push({
      id: `regions:${kind}`,
      label: t('panels:tree.regionKinds.' + kind, { count: regions.length }),
      state: 'ok',
      ref: null,
      testId: `tree-group-regions-${kind}`,
      children: regions.map((region) => ({
        id: `region:${region.id}`,
        label: regionName(region, t),
        secondary:
          region.rms === null
            ? t('panels:regionKind.' + region.kind)
            : t('panels:tree.regionSummary', {
                kind: t('panels:regionKind.' + region.kind),
                rms: format.length(region.rms),
              }),
        icon: `region:${region.kind}`,
        state: 'ok',
        ref: { kind: 'region', id: region.id },
        testId: `tree-node-${region.id}`,
      })),
    });
  }
  return {
    id: 'regions',
    label: t('panels:tree.regions', { count: items.length }),
    icon: 'regions',
    state: 'ok',
    ref: null,
    testId: 'tree-group-regions',
    children: groups,
  };
}

function alignmentEdit(document: Document): { toolId: string; target: string } {
  return {
    toolId: document.alignment.method === 'faces' ? 'align-faces' : 'align-auto',
    target: 'alignment',
  };
}

/** The tree's top-level nodes: Scan, Bereiche, Körper, Ursprung, Verlauf. */
export function buildProjectTree(input: TreeModelInput): ProjectNode[] {
  const { document, status, t, format } = input;
  const scan = document.scan;
  if (!scan) return [];
  const nodes: ProjectNode[] = [
    {
      id: 'scan',
      label: t('panels:tree.scan'),
      secondary: t('panels:tree.faces', {
        count: scan.faceCount,
        formatted: format.count(scan.faceCount),
      }),
      icon: 'scan',
      state: 'ok',
      ref: { kind: 'scan', id: 'scan' },
      testId: 'tree-node-scan',
      children: scan.operations
        .map((operation, index) => ({ operation, index }))
        .filter(({ operation }) => operation.op !== 'import')
        .map(({ operation, index }) => ({
          id: `operation:${index}`,
          label: t('panels:operations.' + operation.op, {
            defaultValue: operation.op,
            count: operation.counts.faces ?? operation.counts.count ?? 0,
            formatted: format.count(operation.counts.faces ?? operation.counts.count ?? 0),
          }),
          icon: 'operation',
          state: 'ok',
          ref: null,
          testId: `tree-node-operation-${index}`,
        })),
    },
  ];

  const regions = regionNodes(input);
  if (regions) nodes.push(regions);

  if (status.bodies.length) {
    nodes.push({
      id: 'bodies',
      label: t('panels:tree.bodies', { count: status.bodies.length }),
      icon: 'bodies',
      state: 'ok',
      ref: null,
      testId: 'tree-group-bodies',
      children: status.bodies.map((body, index) => ({
        id: `body:${body.id}`,
        label: t('panels:tree.body', { number: index + 1 }),
        icon: 'body',
        state: body.valid ? 'ok' : 'error',
        ref: { kind: 'body', id: body.id },
        testId: `tree-node-${body.id}`,
      })),
    });
  }

  nodes.push({
    id: 'origin',
    label: t('panels:tree.origin'),
    icon: 'origin',
    state: 'ok',
    ref: null,
    testId: 'tree-group-origin',
    children: [
      ...(['XY', 'YZ', 'XZ'] as const).map((plane): ProjectNode => ({
        id: `origin:${plane}`,
        label: plane,
        icon: 'plane',
        state: 'ok',
        ref: null,
        testId: `tree-node-origin-${plane}`,
      })),
      {
        id: 'origin:axes',
        label: t('panels:tree.axes'),
        icon: 'axes',
        state: 'ok',
        ref: null,
        testId: 'tree-node-origin-axes',
      },
    ],
  });

  nodes.push({
    id: 'history',
    label: t('panels:tree.history'),
    icon: 'history',
    state: 'ok',
    ref: null,
    testId: 'tree-group-history',
    children: [
      {
        id: 'alignment',
        label: t('panels:tree.alignment'),
        secondary: t('panels:alignmentMethod.' + document.alignment.method),
        icon: 'alignment',
        state: 'ok',
        ref: null,
        edit: alignmentEdit(document),
        testId: 'tree-node-alignment',
      },
      ...document.features.map((feature): ProjectNode => {
        const featureStatus = status.features[feature.id];
        const state: FeatureState = feature.suppressed
          ? 'suppressed'
          : (featureStatus?.state ?? 'ok');
        const editTool = input.editTools.get(feature.type);
        return {
          id: `feature:${feature.id}`,
          label: input.featureNames.get(feature.id) ?? feature.id,
          secondary: input.summaries?.get(feature.id),
          icon: `feature:${feature.type}`,
          state,
          ref: { kind: 'feature', id: feature.id },
          edit: editTool ? { toolId: editTool, target: feature.id } : undefined,
          testId: `tree-node-${feature.id}`,
        };
      }),
    ],
  });
  return nodes;
}

/** Depth-first lookup of a node by id. */
export function findNode(nodes: readonly ProjectNode[], id: string): ProjectNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = node.children ? findNode(node.children, id) : null;
    if (child) return child;
  }
  return null;
}

/** Tree row id of an object reference (`feature:f3`). */
export function nodeIdOf(ref: ObjectRef): string {
  return ref.kind === 'scan' ? 'scan' : `${ref.kind}:${ref.id}`;
}
