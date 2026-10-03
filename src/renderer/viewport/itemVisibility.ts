// Which document items the viewport draws: body edges follow the display mode, the
// feature a tool edits in place is left out, and the project tree hides bodies by body
// id and every other item (sections, planes, sketches) by its owner feature.

import type { SceneItem } from '@shared/protocol/generated/document-display';

export interface ItemVisibility {
  bodyEdges: boolean;
  /** The owner a tool edits in place, or null. */
  editedOwner: string | null;
  hiddenBodies: ReadonlySet<string>;
  hiddenOwners: ReadonlySet<string>;
}

/** Items drawn as part of a body (surfaces and edges), as opposed to construction. */
export function isBodyItem(item: SceneItem): boolean {
  return !!item.bodyId && item.style !== 'construction' && item.style !== 'patch';
}

export function itemShown(item: SceneItem, visibility: ItemVisibility): boolean {
  if (item.style === 'bodyEdges' && !visibility.bodyEdges) return false;
  if (item.owner === visibility.editedOwner) return false;
  return isBodyItem(item)
    ? !visibility.hiddenBodies.has(item.bodyId ?? '')
    : !visibility.hiddenOwners.has(item.owner);
}

/**
 * Body edges that only the display mode hides: a fillet still picks the edge under the
 * pointer in the shaded view. Edges of a hidden body or of the edited feature are not.
 */
export function edgesOnlyModeHides(item: SceneItem, visibility: ItemVisibility): boolean {
  return (
    item.style === 'bodyEdges' &&
    !visibility.bodyEdges &&
    itemShown(item, { ...visibility, bodyEdges: true })
  );
}
