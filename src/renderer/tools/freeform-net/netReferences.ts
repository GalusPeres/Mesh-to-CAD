// The faces a net is pushed past (QuickSurface: every visible primitive): the shown
// fitted and constructed planes and the shown bodies.

import { useMemo } from 'react';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { type HiddenObjects, useHiddenObjects } from '../../panels/objectVisibility';
import { useDocument } from '../../state/documentStore';
import { type Visibility, useView } from '../../state/viewStore';
import { isPlane, usableFeatures } from '../extrude/solid/model';

export interface PushReferences {
  planes: string[];
  bodies: string[];
}

export function visibleReferences(
  snapshot: Pick<DocumentSnapshot, 'document' | 'status'>,
  hidden: HiddenObjects,
  visibility: Visibility,
): PushReferences {
  if (visibility === 'scan') return { planes: [], bodies: [] };
  return {
    planes: usableFeatures(snapshot, isPlane, null).filter((id) => !hidden.owners.includes(id)),
    bodies: snapshot.status.bodies
      .map((body) => body.id)
      .filter((id) => !hidden.bodies.includes(id)),
  };
}

export function referenceCount(references: PushReferences): number {
  return references.planes.length + references.bodies.length;
}

const NONE: PushReferences = { planes: [], bodies: [] };

/** The planes and bodies shown right now. */
export function usePushReferences(): PushReferences {
  const snapshot = useDocument((state) => state.snapshot);
  const hidden = useHiddenObjects((state) => state);
  const visibility = useView((state) => state.visibility);
  return useMemo(
    () => (snapshot ? visibleReferences(snapshot, hidden, visibility) : NONE),
    [snapshot, hidden, visibility],
  );
}
