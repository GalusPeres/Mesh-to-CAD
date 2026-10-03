// The objects chosen in the tree belong to one document. Feature ids repeat across
// projects, so a choice kept into a new project names a different object there (and a
// tool opened next would take it as its input). A new scan or a loaded project starts
// with nothing chosen; objects that are gone drop out of the choice.

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { documentStore } from '../state/documentStore';
import { type ObjectRef, objectSelectionStore, selectObjects } from '../state/objectSelectionStore';

type Snapshot = Pick<DocumentSnapshot, 'cause' | 'document' | 'status'>;

/** Whether the object is part of the document. */
function exists(ref: ObjectRef, snapshot: Snapshot): boolean {
  const { document, status } = snapshot;
  switch (ref.kind) {
    case 'scan':
      return document.scan !== null;
    case 'region':
      return document.regions.items.some((region) => region.id === ref.id);
    case 'feature':
      return document.features.some((feature) => feature.id === ref.id);
    case 'body':
      return status.bodies.some((body) => body.id === ref.id);
  }
}

/** The choice after the document changed from `previous` to `snapshot`. */
export function keptSelection(
  selected: readonly ObjectRef[],
  snapshot: Snapshot,
  previous: Snapshot | null,
): ObjectRef[] {
  const another =
    snapshot.cause === 'restore' || previous?.document.scan?.key !== snapshot.document.scan?.key;
  return another ? [] : selected.filter((ref) => exists(ref, snapshot));
}

/** Keep the tree's choice to the current document; returns the unsubscribe. */
export function connectSelectionReset(): () => void {
  return documentStore.subscribe((state, before) => {
    if (!state.snapshot || state.snapshot === before.snapshot) return;
    const { selected } = objectSelectionStore.getState();
    const kept = keptSelection(selected, state.snapshot, before.snapshot);
    if (kept.length !== selected.length) selectObjects(kept);
  });
}
