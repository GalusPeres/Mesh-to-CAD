import * as ContextMenu from '@radix-ui/react-context-menu';
import {
  Axis3d,
  Ban,
  Box,
  Boxes,
  CircleAlert,
  CircleDashed,
  Cone,
  Crosshair,
  Cylinder,
  FileBox,
  History,
  type LucideIcon,
  Move3d,
  Pencil,
  Shapes,
  Square,
  Torus,
  Trash2,
  TriangleAlert,
  Waves,
  Wrench,
} from 'lucide-react';
import { type KeyboardEvent, type MouseEvent, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import menuStyles from '../ui/Menu/Menu.module.css';
import { FEATURE_VIEWS, featureNames, featureView } from '../features/registry';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import {
  hoverObject,
  selectObjects,
  useObjectSelection,
} from '../state/objectSelectionStore';
import { openTool } from '../tools/framework/toolActions';
import { Checkbox } from '../ui/Checkbox/Checkbox';
import { PlaneIcon, SphereIcon } from '../ui/icons/customIcons';
import { Tree, type TreeNode } from '../ui/Tree/Tree';
import styles from './ProjectTree.module.css';
import { canEditDocument, requestDelete, startRename, toggleSuppressed } from './treeActions';
import { buildProjectTree, findNode, nodeIdOf, type ProjectNode, type ProjectNodeIcon } from './treeModel';
import { setOnlyUnusedRegions, useTreeFilter } from './treeFilterStore';
import { useViewportHighlight } from './viewportHighlight';

const FIXED_ICONS: Record<string, LucideIcon> = {
  scan: FileBox,
  operation: Wrench,
  regions: Shapes,
  bodies: Boxes,
  body: Box,
  origin: Crosshair,
  plane: Square,
  axes: Axis3d,
  history: History,
  alignment: Move3d,
  'region:plane': PlaneIcon,
  'region:cylinder': Cylinder,
  'region:cone': Cone,
  'region:sphere': SphereIcon,
  'region:torus': Torus,
  'region:freeform': Waves,
  'region:unknown': CircleDashed,
};

function iconOf(icon: ProjectNodeIcon | undefined): LucideIcon | undefined {
  if (!icon) return undefined;
  if (icon.startsWith('feature:')) return featureView(icon.slice('feature:'.length))?.icon;
  return FIXED_ICONS[icon];
}

function StateIcon({ node, label }: { node: ProjectNode; label: string }) {
  if (node.state === 'warning') {
    return <TriangleAlert size={16} className={styles.warning} aria-label={label} role="img" />;
  }
  if (node.state === 'error') {
    return <CircleAlert size={16} className={styles.error} aria-label={label} role="img" />;
  }
  if (node.state === 'skipped' || node.state === 'suppressed') {
    return <Ban size={16} className={styles.disabled} aria-label={label} role="img" />;
  }
  return null;
}

/** Open the tool that edits this node (double-click, Enter, context menu). */
function editNode(node: ProjectNode | null): void {
  if (!node?.edit || !canEditDocument()) return;
  void openTool(node.edit.toolId, null, node.edit.target);
}

/**
 * The project tree: object list and history in one (docs/DESIGN.md 5.5).
 * Groups without content are hidden; hover and selection go through
 * objectSelectionStore, which the viewport highlight follows.
 */
export function ProjectTree() {
  const { t } = useTranslation('panels');
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const selected = useObjectSelection((state) => state.selected[0] ?? null);
  const onlyUnused = useTreeFilter((state) => state.onlyUnusedRegions);
  const [menuNodeId, setMenuNodeId] = useState<string | null>(null);
  useViewportHighlight();

  const model = useMemo(() => {
    if (!snapshot?.document.scan) return [];
    const document = snapshot.document;
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
      editTools: new Map(
        [...FEATURE_VIEWS.values()].flatMap((view) =>
          view.editTool ? [[view.type, view.editTool] as const] : [],
        ),
      ),
      summaries,
      onlyUnusedRegions: onlyUnused,
    });
  }, [snapshot, t, format, onlyUnused]);

  if (!model.length) return null;

  const toTreeNode = (node: ProjectNode): TreeNode => ({
    id: node.id,
    label: node.label,
    secondary: node.secondary,
    icon: iconOf(node.icon),
    muted: node.state === 'suppressed' || node.state === 'skipped',
    status: <StateIcon node={node} label={t(`state.${node.state}`)} />,
    children: node.children?.map(toTreeNode),
    testId: node.testId,
  });

  const selectedId = selected ? nodeIdOf(selected) : null;
  const selectedNode = selectedId ? findNode(model, selectedId) : null;
  const menuNode = menuNodeId ? findNode(model, menuNodeId) : null;
  const hasRegions = model.some((node) => node.id === 'regions');

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const featureId = selectedNode?.ref?.kind === 'feature' ? selectedNode.ref.id : null;
    if (!featureId || event.ctrlKey || event.altKey) return;
    if (event.key === 'F2') {
      event.preventDefault();
      startRename(featureId, selectedNode?.label ?? '');
    } else if (event.key === 'Delete') {
      event.preventDefault();
      void requestDelete(featureId);
    }
  };

  const onContextMenu = (event: MouseEvent<HTMLDivElement>) => {
    const row = (event.target as HTMLElement).closest('[role="treeitem"]');
    const testId = row?.getAttribute('data-testid');
    const node = testId ? findByTestId(model, testId) : null;
    setMenuNodeId(node?.id ?? null);
    if (node?.ref) selectObjects([node.ref]);
    if (!node?.edit && node?.ref?.kind !== 'feature') event.preventDefault();
  };

  const menuFeature = menuNode?.ref?.kind === 'feature' ? menuNode.ref.id : null;
  const editable = canEditDocument();

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
          <div onKeyDown={onKeyDown} onContextMenu={onContextMenu} className={styles.tree}>
            <Tree
              label={t('project')}
              nodes={model.map(toTreeNode)}
              selectedId={selectedId}
              defaultExpanded={['scan', 'bodies', 'history']}
              onSelect={(id) => {
                const node = findNode(model, id);
                selectObjects(node?.ref ? [node.ref] : []);
              }}
              onActivate={(id) => editNode(findNode(model, id))}
              onHover={(id) => hoverObject(id ? (findNode(model, id)?.ref ?? null) : null)}
            />
          </div>
        </ContextMenu.Trigger>
        <ContextMenu.Portal>
          <ContextMenu.Content className={menuStyles.content} collisionPadding={8}>
            {menuNode?.edit && (
              <MenuEntry
                icon={Pencil}
                label={t('menu.edit')}
                shortcut="Enter"
                disabled={!editable}
                testId="tree-menu-edit"
                onSelect={() => editNode(menuNode)}
              />
            )}
            {menuFeature && (
              <>
                <MenuEntry
                  label={t('menu.rename')}
                  shortcut="F2"
                  disabled={!editable}
                  testId="tree-menu-rename"
                  onSelect={() => startRename(menuFeature, menuNode?.label ?? '')}
                />
                <MenuEntry
                  icon={Ban}
                  label={t(menuNode?.state === 'suppressed' ? 'menu.unsuppress' : 'menu.suppress')}
                  disabled={!editable}
                  testId="tree-menu-suppress"
                  onSelect={() => void toggleSuppressed(menuFeature)}
                />
                <ContextMenu.Separator className={menuStyles.separator} />
                <MenuEntry
                  icon={Trash2}
                  label={t('menu.delete')}
                  shortcut={t('menu.deleteKey')}
                  disabled={!editable}
                  testId="tree-menu-delete"
                  onSelect={() => void requestDelete(menuFeature)}
                />
              </>
            )}
          </ContextMenu.Content>
        </ContextMenu.Portal>
      </ContextMenu.Root>
    </div>
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

interface MenuEntryProps {
  label: string;
  icon?: LucideIcon;
  shortcut?: string;
  disabled?: boolean;
  testId: string;
  onSelect: () => void;
}

function MenuEntry({ label, icon: Icon, shortcut, disabled, testId, onSelect }: MenuEntryProps) {
  return (
    <ContextMenu.Item
      className={menuStyles.item}
      disabled={disabled}
      data-testid={testId}
      onSelect={onSelect}
    >
      <span className={menuStyles.icon} aria-hidden>
        {Icon && <Icon size={16} />}
      </span>
      <span className={menuStyles.label}>{label}</span>
      {shortcut && <span className={menuStyles.shortcut}>{shortcut}</span>}
    </ContextMenu.Item>
  );
}
