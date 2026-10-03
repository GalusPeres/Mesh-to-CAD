import * as ContextMenu from '@radix-ui/react-context-menu';
import { Ban, CircleAlert, Eye, EyeOff, TriangleAlert } from 'lucide-react';
import { type KeyboardEvent, type MouseEvent, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { matchesShortcut } from '../app/commands/keymap';
import { featureNames, featureView } from '../features/registry';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { hoverObject, selectObjects, useObjectSelection } from '../state/objectSelectionStore';
import { useView } from '../state/viewStore';
import { TOOLS } from '../tools/framework/registry';
import { Checkbox } from '../ui/Checkbox/Checkbox';
import { IconButton } from '../ui/IconButton/IconButton';
import { Tree, type TreeNode } from '../ui/Tree/Tree';
import { useViewport } from '../viewport/api';
import { featureEditTools } from './editTools';
import {
  canHide,
  isHidden,
  somethingHidden,
  toggleHidden,
  useHiddenObjects,
} from './objectVisibility';
import styles from './ProjectTree.module.css';
import { runTreeAction, TreeContextMenu } from './TreeContextMenu';
import { setOnlyUnusedRegions, useTreeFilter } from './treeFilterStore';
import { treeIcon } from './treeIcons';
import { TREE_KEYS, type TreeMenuAction, treeMenuActions } from './treeMenu';
import {
  buildProjectTree,
  DEFAULT_EXPANDED,
  findNode,
  nodeIdOf,
  type ProjectNode,
} from './treeModel';
import { useViewportSync } from './viewportSync';

const EDIT_TOOLS = featureEditTools(undefined, TOOLS);

function StateIcon({ state, label }: { state: ProjectNode['state']; label: string }) {
  const props = { size: 16, role: 'img', 'aria-label': label } as const;
  if (state === 'warning') return <TriangleAlert {...props} className={styles.warning} />;
  if (state === 'error') return <CircleAlert {...props} className={styles.error} />;
  if (state === 'skipped' || state === 'suppressed') {
    return <Ban {...props} className={styles.disabled} />;
  }
  return null;
}

/** Tree rows need the document plus the formatter and translations for names and summaries. */
function useProjectModel(snapshot: DocumentSnapshot | null, onlyUnused: boolean): ProjectNode[] {
  const { t } = useTranslation('panels');
  const format = useFormatter();
  return useMemo(() => {
    const document = snapshot?.document;
    if (!document?.scan || !snapshot) return [];
    const summaries = new Map<string, string>();
    for (const feature of document.features) {
      const summary = featureView(feature.type)?.summary?.(feature.params as never, format, t);
      if (summary) summaries.set(feature.id, summary);
    }
    return buildProjectTree({
      document,
      status: snapshot.status,
      t,
      format,
      featureNames: featureNames(document.features, t),
      editTools: EDIT_TOOLS,
      summaries,
      onlyUnusedRegions: onlyUnused,
    });
  }, [snapshot, t, format, onlyUnused]);
}

/**
 * The project tree: object list and history in one (docs/DESIGN.md 5.5). Hover and
 * selection go through objectSelectionStore, which the viewport follows and writes.
 */
export function ProjectTree() {
  const { t } = useTranslation('panels');
  const snapshot = useDocument((state) => state.snapshot);
  const selected = useObjectSelection((state) => state.selected[0] ?? null);
  const onlyUnused = useTreeFilter((state) => state.onlyUnusedRegions);
  const hidden = useHiddenObjects((state) => state);
  const visibility = useView((state) => state.visibility);
  const viewport = useViewport();
  const [menuNodeId, setMenuNodeId] = useState<string | null>(null);
  useViewportSync();
  const model = useProjectModel(snapshot, onlyUnused);

  if (!model.length || !snapshot) return null;

  const menuContext = (node: ProjectNode) => ({
    hidden: !!node.ref && isHidden(node.ref, hidden, visibility),
    canHide: !!node.ref && canHide(node.ref, viewport),
    anythingHidden: somethingHidden(hidden, visibility),
  });

  const toTreeNode = (node: ProjectNode): TreeNode => {
    const rowHidden = !!node.ref && isHidden(node.ref, hidden, visibility);
    return {
      id: node.id,
      label: node.label,
      secondary: node.secondary,
      icon: treeIcon(node.icon),
      muted: node.state === 'suppressed' || node.state === 'skipped',
      status: (
        <>
          <StateIcon state={node.state} label={t(`state.${node.state}`)} />
          {node.ref && canHide(node.ref, viewport) && (
            <VisibilityToggle node={node} hidden={rowHidden} snapshot={snapshot} />
          )}
        </>
      ),
      children: node.children?.map(toTreeNode),
      testId: node.testId,
    };
  };

  const selectedId = selected ? nodeIdOf(selected) : null;
  const selectedNode = selectedId ? findNode(model, selectedId) : null;
  const menuNode = menuNodeId ? findNode(model, menuNodeId) : null;
  const menuGroups = menuNode ? treeMenuActions(menuNode, menuContext(menuNode)) : [];
  const hasRegions = model.some((node) => node.id === 'regions');

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!selectedNode) return;
    const available = treeMenuActions(selectedNode, menuContext(selectedNode)).flat();
    const action = (['rename', 'delete', 'hide', 'show'] as const).find(
      (candidate: TreeMenuAction) => {
        const shortcut = TREE_KEYS[candidate];
        return available.includes(candidate) && !!shortcut && matchesShortcut(event, shortcut);
      },
    );
    if (!action) return;
    // Handled here, so the viewport commands on the same keys (Entf, H) do not run.
    event.preventDefault();
    runTreeAction(action, selectedNode, snapshot);
  };

  const onContextMenu = (event: MouseEvent<HTMLDivElement>) => {
    const row = (event.target as HTMLElement).closest('[role="treeitem"]');
    const node = findByTestId(model, row?.getAttribute('data-testid') ?? '');
    setMenuNodeId(node?.id ?? null);
    if (node?.ref) selectObjects([node.ref]);
    if (!node || treeMenuActions(node, menuContext(node)).length === 0) event.preventDefault();
  };

  return (
    <div className={styles.panel}>
      {hasRegions && (
        <div className={styles.filter}>
          <Checkbox
            checked={onlyUnused}
            label={t('tree.onlyUnused')}
            testId="tree-filter-unused"
            onChange={setOnlyUnusedRegions}
          />
        </div>
      )}
      <ContextMenu.Root modal={false}>
        <ContextMenu.Trigger asChild>
          <div className={styles.tree} onKeyDown={onKeyDown} onContextMenu={onContextMenu}>
            <Tree
              label={t('project')}
              nodes={model.map(toTreeNode)}
              selectedId={selectedId}
              defaultExpanded={DEFAULT_EXPANDED}
              onSelect={(id) => {
                const node = findNode(model, id);
                selectObjects(node?.ref ? [node.ref] : []);
              }}
              onActivate={(id) => {
                const node = findNode(model, id);
                if (node?.edit) runTreeAction('edit', node, snapshot);
              }}
              onHover={(id) => hoverObject(id ? (findNode(model, id)?.ref ?? null) : null)}
            />
          </div>
        </ContextMenu.Trigger>
        <ContextMenu.Portal>
          {menuNode && menuGroups.length > 0 && (
            <TreeContextMenu node={menuNode} groups={menuGroups} snapshot={snapshot} />
          )}
        </ContextMenu.Portal>
      </ContextMenu.Root>
    </div>
  );
}

function VisibilityToggle({
  node,
  hidden,
  snapshot,
}: {
  node: ProjectNode;
  hidden: boolean;
  snapshot: DocumentSnapshot;
}) {
  const { t } = useTranslation('panels');
  const ref = node.ref;
  if (!ref) return null;
  return (
    <IconButton
      icon={hidden ? EyeOff : Eye}
      label={t(hidden ? 'menu.show' : 'menu.hide')}
      shortcut="H"
      pressed={hidden}
      className={hidden ? styles.eyeHidden : styles.eye}
      data-testid={`tree-eye-${node.testId.replace(/^tree-node-/, '')}`}
      onClick={(event) => {
        event.stopPropagation();
        toggleHidden(ref, snapshot);
      }}
      onDoubleClick={(event) => event.stopPropagation()}
    />
  );
}

function findByTestId(nodes: readonly ProjectNode[], testId: string): ProjectNode | null {
  for (const node of nodes) {
    if (node.testId === testId) return node;
    const child = node.children ? findByTestId(node.children, testId) : null;
    if (child) return child;
  }
  return null;
}
