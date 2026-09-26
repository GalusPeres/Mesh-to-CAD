import type { Shortcut } from '../app/commands/types';
import type { ProjectNode } from './treeModel';

export type TreeMenuAction =
  | 'edit'
  | 'rename'
  | 'hide'
  | 'show'
  | 'isolate'
  | 'showAll'
  | 'suppress'
  | 'unsuppress'
  | 'delete';

export interface TreeMenuContext {
  /** The row's object is hidden in the viewport. */
  hidden: boolean;
  /** The viewport can hide the row's object. */
  canHide: boolean;
  /** Anything at all is hidden, so *Alle einblenden* has an effect. */
  anythingHidden: boolean;
}

/**
 * Context-menu entries of a tree row in the order of docs/DESIGN.md 5.5, grouped for
 * separators: Bearbeiten, Umbenennen · Ausblenden, Isolieren, Alle einblenden ·
 * Unterdrücken · Löschen. Rows without entries get no menu.
 */
export function treeMenuActions(node: ProjectNode, context: TreeMenuContext): TreeMenuAction[][] {
  const feature = node.ref?.kind === 'feature';
  const edit: TreeMenuAction[] = [
    ...(node.edit ? (['edit'] as const) : []),
    ...(feature ? (['rename'] as const) : []),
  ];
  const visibility: TreeMenuAction[] =
    node.ref && context.canHide ? [context.hidden ? 'show' : 'hide', 'isolate'] : [];
  if (visibility.length && context.anythingHidden) visibility.push('showAll');
  const suppress: TreeMenuAction[] = feature
    ? [node.state === 'suppressed' ? 'unsuppress' : 'suppress']
    : [];
  const remove: TreeMenuAction[] = feature ? ['delete'] : [];
  return [edit, visibility, suppress, remove].filter((group) => group.length > 0);
}

/**
 * Keys the tree handles itself while it has focus. They take precedence over the
 * viewport commands on the same keys (Entf deletes triangles, H hides the selection).
 */
export const TREE_KEYS: Partial<Record<TreeMenuAction, Shortcut>> = {
  edit: { key: 'Enter' },
  rename: { key: 'F2' },
  hide: { key: 'h' },
  show: { key: 'h' },
  delete: { key: 'Delete' },
};
