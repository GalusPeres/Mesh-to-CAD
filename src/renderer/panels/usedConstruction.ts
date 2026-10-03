// Construction a later feature has used is hidden, as CAD programs do: a sketch once it
// is extruded, a plane once it is sketched on, a loft's sections once a later feature
// changes its body. What is left in view is the result. The drawings are hidden once,
// through the tree's hidden list, so the eye in the tree shows them again; when the use
// is undone, they come back by themselves.

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { documentStore } from '../state/documentStore';
import { type HiddenObjects, objectVisibilityStore } from './objectVisibility';

/** Features whose id appears in the parameters of a later feature. */
export function usedFeatures(snapshot: Pick<DocumentSnapshot, 'document'>): Set<string> {
  const features = snapshot.document.features;
  const used = new Set<string>();
  features.forEach((feature, index) => {
    const earlier = new Set(features.slice(0, index).map((item) => item.id));
    collect(feature.params, earlier, used);
  });
  return used;
}

function collect(value: unknown, ids: ReadonlySet<string>, used: Set<string>): void {
  if (typeof value === 'string') {
    if (ids.has(value)) used.add(value);
  } else if (Array.isArray(value)) {
    for (const item of value) collect(item, ids, used);
  } else if (value !== null && typeof value === 'object') {
    for (const item of Object.values(value)) collect(item, ids, used);
  }
}

/**
 * The hidden lists after the document changed: newly used features are hidden, and
 * ones this module hid that are no longer used are shown again. `hiddenByUse` keeps
 * track of what this module hid and is updated in place.
 */
export function afterUse(
  hidden: HiddenObjects,
  used: ReadonlySet<string>,
  hiddenByUse: Set<string>,
): HiddenObjects {
  const owners = new Set(hidden.owners);
  for (const id of used) {
    if (hiddenByUse.has(id)) continue;
    hiddenByUse.add(id);
    owners.add(id);
  }
  for (const id of [...hiddenByUse]) {
    if (used.has(id)) continue;
    hiddenByUse.delete(id);
    owners.delete(id);
  }
  return owners.size === hidden.owners.length &&
    [...owners].every((id) => hidden.owners.includes(id))
    ? hidden
    : { ...hidden, owners: [...owners] };
}

/** Hide used construction whenever the document changes; returns the unsubscribe. */
export function connectUsedConstruction(): () => void {
  const hiddenByUse = new Set<string>();
  const update = (snapshot: DocumentSnapshot | null) => {
    if (!snapshot) return;
    const hidden = objectVisibilityStore.getState();
    // A new or opened project starts over (feature ids repeat across projects): what
    // the last one hid by use is shown again, or its ids would hide new features.
    const fresh = snapshot.cause === 'restore' || snapshot.document.features.length === 0;
    const kept = fresh ? afterUse(hidden, new Set(), hiddenByUse) : hidden;
    const next = afterUse(kept, usedFeatures(snapshot), hiddenByUse);
    if (next !== hidden) objectVisibilityStore.setState(next, true);
  };
  update(documentStore.getState().snapshot);
  return documentStore.subscribe((state) => update(state.snapshot));
}
