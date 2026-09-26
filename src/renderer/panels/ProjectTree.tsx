import { Axis3d, Box, FileBox, Shapes } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { featureNames, featureView } from '../features/registry';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { selectObjects, useObjectSelection } from '../state/objectSelectionStore';
import { Tree, type TreeNode } from '../ui/Tree/Tree';

/**
 * The project tree: object list and history in one (docs/DESIGN.md 5.5).
 * Groups without content are hidden.
 */
export function ProjectTree() {
  const { t } = useTranslation('panels');
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const selected = useObjectSelection((state) => state.selected[0] ?? null);
  if (!snapshot?.document.scan) return null;

  const document = snapshot.document;
  const names = featureNames(document.features, t);
  const scan = snapshot.document.scan;
  const nodes: TreeNode[] = [
    {
      id: 'scan',
      label: t('tree.scan'),
      secondary: t('tree.faces', {
        count: scan.faceCount,
        formatted: format.count(scan.faceCount),
      }),
      icon: FileBox,
      testId: 'tree-node-scan',
    },
  ];
  if (document.regions.items.length) {
    nodes.push({
      id: 'regions',
      label: t('tree.regions', { count: document.regions.items.length }),
      icon: Shapes,
      children: document.regions.items.map((region) => ({
        id: `region:${region.id}`,
        label: region.name ?? t('tree.region', { number: region.label }),
        testId: `tree-node-${region.id}`,
      })),
    });
  }
  const bodies = snapshot.status.bodies;
  if (bodies.length) {
    nodes.push({
      id: 'bodies',
      label: t('tree.bodies', { count: bodies.length }),
      icon: Box,
      children: bodies.map((body, index) => ({
        id: `body:${body.id}`,
        label: t('tree.body', { number: index + 1 }),
        testId: `tree-node-${body.id}`,
      })),
    });
  }
  nodes.push({
    id: 'history',
    label: t('tree.history'),
    children: [
      { id: 'alignment', label: t('tree.alignment'), icon: Axis3d, testId: 'tree-node-alignment' },
      ...document.features.map((feature) => {
        const state = snapshot.status.features[feature.id]?.state;
        return {
          id: `feature:${feature.id}`,
          label: names.get(feature.id) ?? feature.id,
          icon: featureView(feature.type)?.icon,
          muted: state === 'suppressed' || state === 'skipped',
          testId: `tree-node-${feature.id}`,
        };
      }),
    ],
  });

  const selectedId = selected ? `${selected.kind}:${selected.id}` : null;
  return (
    <Tree
      label={t('project')}
      nodes={nodes}
      selectedId={selectedId}
      defaultExpanded={['history', 'bodies']}
      onSelect={(id) => {
        const [kind, objectId] = id.split(':');
        if (objectId && (kind === 'feature' || kind === 'body' || kind === 'region')) {
          selectObjects([{ kind, id: objectId }]);
        } else if (id === 'scan') {
          selectObjects([{ kind: 'scan', id: 'scan' }]);
        }
      }}
    />
  );
}
