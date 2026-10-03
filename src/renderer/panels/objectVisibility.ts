// Visibility of project objects, toggled from the tree (eye button, H, Isolieren).
//
// The scan is shown or hidden through viewStore.visibility, the same switch that
// Space cycles, so both stay consistent. Single bodies and feature items (fitted
// shapes, sketches) are hidden through `Viewport.setHiddenObjects`; that member is
// an open interface request (.work/interface-requests/T9.md), so the tree only offers
// hiding them when the mounted viewport provides it.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import type { ObjectRef } from '../state/objectSelectionStore';
import { setVisibility, viewStore, type Visibility } from '../state/viewStore';
import { getViewport, type Viewport } from '../viewport/api';

/**
 * Objects the viewport leaves out. A body item is hidden by its body id, any other
 * item (construction, sketch) by its owner feature.
 */
export interface HiddenObjects {
  bodies: readonly string[];
  owners: readonly string[];
}

interface ObjectHiding {
  setHiddenObjects(hidden: HiddenObjects): void;
}

export function supportsObjectHiding(
  viewport: Viewport | null,
): viewport is Viewport & ObjectHiding {
  return typeof (viewport as Partial<ObjectHiding> | null)?.setHiddenObjects === 'function';
}

export const EMPTY_HIDDEN: HiddenObjects = { bodies: [], owners: [] };

export const objectVisibilityStore = createStore<HiddenObjects>(() => EMPTY_HIDDEN);

export function useHiddenObjects<T>(selector: (state: HiddenObjects) => T): T {
  return useStore(objectVisibilityStore, selector);
}

/** Whether the tree can hide this kind of object in the current viewport. */
export function canHide(ref: ObjectRef, viewport: Viewport | null = getViewport()): boolean {
  if (ref.kind === 'scan') return true;
  return (ref.kind === 'body' || ref.kind === 'feature') && supportsObjectHiding(viewport);
}

export function isHidden(ref: ObjectRef, hidden: HiddenObjects, visibility: Visibility): boolean {
  switch (ref.kind) {
    case 'scan':
      return visibility === 'bodies';
    case 'body':
      return visibility === 'scan' || hidden.bodies.includes(ref.id);
    case 'feature':
      return visibility === 'scan' || hidden.owners.includes(ref.id);
    default:
      return false;
  }
}

function toggled(list: readonly string[], id: string): string[] {
  return list.includes(id) ? list.filter((item) => item !== id) : [...list, id];
}

/** Hidden objects after showing or hiding one body or feature. */
export function toggleInList(hidden: HiddenObjects, ref: ObjectRef): HiddenObjects {
  if (ref.kind === 'body') return { ...hidden, bodies: toggled(hidden.bodies, ref.id) };
  if (ref.kind === 'feature') return { ...hidden, owners: toggled(hidden.owners, ref.id) };
  return hidden;
}

/**
 * What stays visible when one object is isolated: only that object. Isolating the
 * scan hides every body and feature item; isolating anything else hides the scan.
 */
export function isolation(
  ref: ObjectRef,
  snapshot: DocumentSnapshot,
): { hidden: HiddenObjects; visibility: Visibility } {
  if (ref.kind === 'scan') return { hidden: EMPTY_HIDDEN, visibility: 'scan' };
  const bodies = snapshot.status.bodies.map((body) => body.id);
  const owners = snapshot.document.features.map((feature) => feature.id);
  return {
    hidden: {
      bodies: bodies.filter((id) => !(ref.kind === 'body' && id === ref.id)),
      owners: owners.filter((id) => !(ref.kind === 'feature' && id === ref.id)),
    },
    visibility: 'bodies',
  };
}

function scanShown(visibility: Visibility, shown: boolean): Visibility {
  if (shown) return visibility === 'bodies' ? 'both' : visibility;
  return visibility === 'scan' ? 'scan' : 'bodies';
}

export function toggleHidden(ref: ObjectRef, snapshot: DocumentSnapshot): void {
  const visibility = viewStore.getState().visibility;
  if (ref.kind === 'scan') {
    setVisibility(scanShown(visibility, visibility === 'bodies'));
    return;
  }
  if (!canHide(ref)) return;
  if (visibility === 'scan') {
    // All items are switched off as a whole (Space). Showing one object shows only
    // that one, which is what the eye button promises.
    objectVisibilityStore.setState(isolation(ref, snapshot).hidden, true);
    setVisibility('both');
    return;
  }
  objectVisibilityStore.setState(toggleInList(objectVisibilityStore.getState(), ref), true);
}

export function isolate(ref: ObjectRef, snapshot: DocumentSnapshot): void {
  if (ref.kind !== 'scan' && !canHide(ref)) return;
  const { hidden, visibility } = isolation(ref, snapshot);
  objectVisibilityStore.setState(hidden, true);
  setVisibility(visibility);
}

export function showAll(): void {
  objectVisibilityStore.setState(EMPTY_HIDDEN, true);
  setVisibility('both');
}

export function somethingHidden(hidden: HiddenObjects, visibility: Visibility): boolean {
  return visibility !== 'both' || hidden.bodies.length > 0 || hidden.owners.length > 0;
}

/** Forward the hidden lists to the viewport whenever they or the viewport change. */
export function connectObjectVisibility(viewport: Viewport | null): () => void {
  if (!supportsObjectHiding(viewport)) return () => undefined;
  viewport.setHiddenObjects(objectVisibilityStore.getState());
  return objectVisibilityStore.subscribe((hidden) => viewport.setHiddenObjects(hidden));
}
