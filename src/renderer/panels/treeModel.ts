// Pure model of the project tree (docs/DESIGN.md 5.5): which groups exist, their
// order, default names and the region grouping. The React component only adds
// icons and wires the events, so everything here is testable without a DOM.

import type { TFunction } from 'i18next';

import type {
  Document,
  Region,
  RegionKind,
  ScanOperation,
} from '@shared/protocol/generated/document-model';
import type { FeatureState } from '@shared/protocol/generated/document-results';
import type { DocumentStatus } from '@shared/protocol/generated/document-snapshot';

import type { Formatter } from '../i18n/format';
import type { ObjectRef } from '../state/objectSelectionStore';
import { shownStatus } from './featureState';
import { usedFeatures } from './usedConstruction';

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

/** A tool opened by double-click or Enter, with the feature (or `alignment`) it edits. */
export interface EditTarget {
  toolId: string;
  target: string;
}

export interface ProjectNode {
  id: string;
  label: string;
  secondary?: string;
  icon?: ProjectNodeIcon;
  /** Feature state; `ok` for everything that is not a feature. */
  state: FeatureState;
  /** The object this row stands for; groups and origin entries have none. */
  ref: ObjectRef | null;
  edit?: EditTarget;
  children?: ProjectNode[];
  testId: string;
}

export interface TreeModelInput {
  document: Document;
  status: DocumentStatus;
  t: TFunction;
  format: Formatter;
  /** Display names from `featureNames` (the user's name, or type plus ordinal). */
  featureNames: ReadonlyMap<string, string>;
  /** Tool that edits a feature type (`FeatureView.editTool` or `ToolDefinition.edits`). */
  editTools: ReadonlyMap<string, string>;
  /** One-line summaries from the feature views, by feature id. */
  summaries: ReadonlyMap<string, string>;
  onlyUnusedRegions: boolean;
}

/** Tree rows that are open when the tree first shows a document. Bereiche stays collapsed. */
export const DEFAULT_EXPANDED: readonly string[] = ['scan', 'bodies', 'history'];

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

/** "Bereich 7": regions are named by their label; the type is the icon, never the name. */
export function regionName(region: Region, t: TFunction): string {
  return region.name ?? t('panels:tree.region', { number: region.label });
}

/** "Körper 2": bodies are numbered in the order the rebuild produced them. */
export function bodyNames(status: DocumentStatus, t: TFunction): Map<string, string> {
  return new Map(
    status.bodies.map((body, index) => [body.id, t('panels:tree.body', { number: index + 1 })]),
  );
}

/** One line of the scan's preparation log: "Reduziert auf 1.000.000 Dreiecke". */
export function operationLabel(operation: ScanOperation, t: TFunction, format: Formatter): string {
  const counts = operation.counts;
  const count = (key: string) => counts[key] ?? 0;
  switch (operation.op) {
    case 'decimate':
      return t('panels:operations.decimate', {
        count: count('facesAfter'),
        formatted: format.count(count('facesAfter')),
      });
    case 'removeSmallParts':
      return t('panels:operations.removeSmallParts', {
        count: count('removedParts'),
        formatted: format.count(count('removedParts')),
      });
    case 'fillHoles':
      return t('panels:operations.fillHoles', {
        count: count('filledHoles'),
        formatted: format.count(count('filledHoles')),
      });
    case 'deleteFaces':
      return t('panels:operations.deleteFaces', {
        count: count('deletedFaces'),
        formatted: format.count(count('deletedFaces')),
      });
    case 'repair':
      return t('panels:operations.repair');
    default:
      return t('panels:operations.other');
  }
}

function scanNode(document: Document, t: TFunction, format: Formatter): ProjectNode | null {
  const scan = document.scan;
  if (!scan) return null;
  return {
    id: 'scan',
    label: t('panels:tree.scan'),
    secondary: t('panels:tree.scanSummary', {
      file: scan.source.fileName,
      faces: t('panels:tree.faces', {
        count: scan.faceCount,
        formatted: format.count(scan.faceCount),
      }),
    }),
    icon: 'scan',
    state: 'ok',
    ref: { kind: 'scan', id: 'scan' },
    testId: 'tree-node-scan',
    children: scan.operations.flatMap((operation, index): ProjectNode[] =>
      operation.op === 'import'
        ? []
        : [
            {
              id: `operation:${index}`,
              label: operationLabel(operation, t, format),
              icon: 'operation',
              state: 'ok',
              ref: null,
              testId: `tree-node-operation-${index}`,
            },
          ],
    ),
  };
}

function regionsNode(input: TreeModelInput): ProjectNode | null {
  const { document, t, format } = input;
  const items = document.regions.items;
  if (!items.length) return null;
  const used = input.onlyUnusedRegions ? usedRegionIds(document) : new Set<string>();
  const visible = items.filter((region) => !used.has(region.id));
  const groups = REGION_KIND_ORDER.flatMap((kind): ProjectNode[] => {
    const regions = visible
      .filter((region) => region.kind === kind)
      .sort((a, b) => a.label - b.label);
    if (!regions.length) return [];
    const kindName = t(`panels:regionKind.${kind}`);
    return [
      {
        id: `regions:${kind}`,
        label: t(`panels:tree.regionKinds.${kind}`, { count: regions.length }),
        state: 'ok',
        ref: null,
        testId: `tree-group-regions-${kind}`,
        children: regions.map((region) => ({
          id: `region:${region.id}`,
          label: regionName(region, t),
          secondary:
            region.rms === null
              ? kindName
              : t('panels:tree.regionSummary', { kind: kindName, rms: format.length(region.rms) }),
          icon: `region:${region.kind}`,
          state: 'ok',
          ref: { kind: 'region', id: region.id },
          testId: `tree-node-${region.id}`,
        })),
      },
    ];
  });
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

function bodiesNode(input: TreeModelInput): ProjectNode | null {
  const { status, t } = input;
  if (!status.bodies.length) return null;
  const names = bodyNames(status, t);
  return {
    id: 'bodies',
    label: t('panels:tree.bodies', { count: status.bodies.length }),
    icon: 'bodies',
    state: 'ok',
    ref: null,
    testId: 'tree-group-bodies',
    children: status.bodies.map((body) => ({
      id: `body:${body.id}`,
      label: names.get(body.id) ?? body.id,
      secondary: input.featureNames.get(body.owner),
      icon: 'body',
      state: body.valid ? 'ok' : 'error',
      ref: { kind: 'body', id: body.id },
      // Body ids equal the ids of the features that created them, hence the prefix.
      testId: `tree-node-body-${body.id}`,
    })),
  };
}

function originNode(t: TFunction): ProjectNode {
  return {
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
  };
}

/** The alignment slot opens the tool that created it; faces alignments need their inputs. */
export function alignmentEditTarget(document: Document): EditTarget {
  return {
    toolId: document.alignment.method === 'faces' ? 'align-faces' : 'align-auto',
    target: 'alignment',
  };
}

function historyNode(input: TreeModelInput): ProjectNode {
  const { document, status, t } = input;
  const used = usedFeatures({ document });
  const features = document.features.map((feature): ProjectNode => {
    const { state } = shownStatus(feature, status.features[feature.id], used);
    const toolId = input.editTools.get(feature.type);
    return {
      id: `feature:${feature.id}`,
      label: input.featureNames.get(feature.id) ?? feature.id,
      secondary: input.summaries.get(feature.id),
      icon: `feature:${feature.type}`,
      state,
      ref: { kind: 'feature', id: feature.id },
      edit: toolId ? { toolId, target: feature.id } : undefined,
      testId: `tree-node-${feature.id}`,
    };
  });
  return {
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
        secondary: t(`panels:alignmentMethod.${document.alignment.method}`),
        icon: 'alignment',
        state: 'ok',
        ref: null,
        edit: alignmentEditTarget(document),
        testId: 'tree-node-alignment',
      },
      ...features,
    ],
  };
}

/** The top-level rows: Scan, Bereiche, Körper, Ursprung, Verlauf. Empty groups are left out. */
export function buildProjectTree(input: TreeModelInput): ProjectNode[] {
  const scan = scanNode(input.document, input.t, input.format);
  if (!scan) return [];
  return [
    scan,
    regionsNode(input),
    bodiesNode(input),
    originNode(input.t),
    historyNode(input),
  ].filter((node): node is ProjectNode => node !== null);
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
