import * as ContextMenu from '@radix-ui/react-context-menu';
import { Ban, Eye, EyeOff, Focus, type LucideIcon, Pencil, Trash2 } from 'lucide-react';
import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { formatShortcut } from '../app/commands/keymap';
import { openTool } from '../tools/framework/toolActions';
import menuStyles from '../ui/Menu/Menu.module.css';
import { isolate, showAll, toggleHidden } from './objectVisibility';
import { canEditDocument, requestDelete, startRename, toggleSuppressed } from './treeActions';
import { TREE_KEYS, type TreeMenuAction } from './treeMenu';
import type { ProjectNode } from './treeModel';

const ICONS: Partial<Record<TreeMenuAction, LucideIcon>> = {
  edit: Pencil,
  hide: EyeOff,
  show: Eye,
  isolate: Focus,
  suppress: Ban,
  unsuppress: Ban,
  delete: Trash2,
};

const DOCUMENT_EDITS: ReadonlySet<TreeMenuAction> = new Set([
  'edit',
  'rename',
  'suppress',
  'unsuppress',
  'delete',
]);

/** Carry out a tree action on a row (context menu and keyboard). */
export function runTreeAction(
  action: TreeMenuAction,
  node: ProjectNode,
  snapshot: DocumentSnapshot,
): void {
  const ref = node.ref;
  const featureId = ref?.kind === 'feature' ? ref.id : null;
  if (DOCUMENT_EDITS.has(action) && !canEditDocument()) return;
  switch (action) {
    case 'edit':
      if (node.edit) void openTool(node.edit.toolId, null, node.edit.target);
      break;
    case 'rename':
      if (featureId) startRename(featureId, node.label);
      break;
    case 'hide':
    case 'show':
      if (ref) toggleHidden(ref, snapshot);
      break;
    case 'isolate':
      if (ref) isolate(ref, snapshot);
      break;
    case 'showAll':
      showAll();
      break;
    case 'suppress':
    case 'unsuppress':
      if (featureId) void toggleSuppressed(featureId);
      break;
    case 'delete':
      if (featureId) void requestDelete(featureId);
      break;
  }
}

interface TreeContextMenuProps {
  node: ProjectNode;
  groups: TreeMenuAction[][];
  snapshot: DocumentSnapshot;
}

export function TreeContextMenu({ node, groups, snapshot }: TreeContextMenuProps) {
  const { t, i18n } = useTranslation('panels');
  const editable = canEditDocument();
  return (
    <ContextMenu.Content className={menuStyles.content} collisionPadding={8}>
      {groups.map((group, index) => (
        <Fragment key={group.join()}>
          {index > 0 && <ContextMenu.Separator className={menuStyles.separator} />}
          {group.map((action) => {
            const Icon = ICONS[action];
            const shortcut = TREE_KEYS[action];
            return (
              <ContextMenu.Item
                key={action}
                className={menuStyles.item}
                disabled={DOCUMENT_EDITS.has(action) && !editable}
                data-testid={`tree-menu-${action}`}
                onSelect={() => runTreeAction(action, node, snapshot)}
              >
                <span className={menuStyles.icon} aria-hidden>
                  {Icon && <Icon size={16} />}
                </span>
                <span className={menuStyles.label}>{t(`menu.${action}`)}</span>
                {shortcut && (
                  <span className={menuStyles.shortcut}>
                    {formatShortcut(shortcut, i18n.language)}
                  </span>
                )}
              </ContextMenu.Item>
            );
          })}
        </Fragment>
      ))}
    </ContextMenu.Content>
  );
}
