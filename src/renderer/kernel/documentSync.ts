import type { KernelStatus, Unsubscribe } from '@shared/bridge';
import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { documentStore, setDocumentSnapshot } from '../state/documentStore';
import { clearHistory, recordHistory } from '../state/historyStore';
import { setKernelStatus } from '../state/jobStore';
import { kernel } from './kernel';

/**
 * Keeps the document mirror current: applies every `documentChanged` event and
 * fetches the document whenever the kernel (re)starts.
 */
export function startDocumentSync(): Unsubscribe {
  const bridge = window.m2c.kernel;

  const onStatus = (status: KernelStatus) => {
    setKernelStatus(status);
    if (status.state === 'ready') {
      kernel()
        .call('doc.get', {})
        .result.then(applySnapshot)
        .catch((error: unknown) => window.m2c.app.log({ level: 'error', message: String(error) }));
    }
  };

  const unsubscribeStatus = bridge.onStatus(onStatus);
  const unsubscribeEvents = bridge.onEvent((event) => {
    if (event.type === 'documentChanged') applySnapshot(event.data as DocumentSnapshot);
  });
  void bridge.status().then(onStatus);

  return () => {
    unsubscribeStatus();
    unsubscribeEvents();
  };
}

export function applySnapshot(snapshot: DocumentSnapshot): void {
  const previous = documentStore.getState().snapshot;
  if (snapshot.cause === 'commit' && previous && previous.revision !== snapshot.revision) {
    recordHistory({ kind: 'document', from: previous.revision, to: snapshot.revision });
  } else if (snapshot.cause === 'restore') {
    clearHistory();
  }
  setDocumentSnapshot(snapshot);
}
