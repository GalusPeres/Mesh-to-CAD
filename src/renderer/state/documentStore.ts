import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

/** Read-only mirror of the kernel's document. Only `kernel/documentSync.ts` writes it. */
export interface DocumentState {
  snapshot: DocumentSnapshot | null;
}

export const documentStore = createStore<DocumentState>(() => ({ snapshot: null }));

export function useDocument<T>(selector: (state: DocumentState) => T): T {
  return useStore(documentStore, selector);
}

export function setDocumentSnapshot(snapshot: DocumentSnapshot | null): void {
  documentStore.setState({ snapshot });
}

export function currentRevision(): number | null {
  return documentStore.getState().snapshot?.revision ?? null;
}
