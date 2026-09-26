// Installs the end-to-end test hooks (src/shared/testHooks.ts). They use only
// stable APIs (stores and viewport/api.ts), never component internals.

import type { TestHooks } from '@shared/testHooks';

import { replaceSelection } from '../selection/api';
import { documentStore } from '../state/documentStore';
import { jobStore } from '../state/jobStore';
import { getViewport } from '../viewport/api';

export function installTestHooks(): void {
  const scene = () => getViewport()?.stats() ?? { scanFaces: 0, items: 0 };
  const hooks: TestHooks = {
    revision: () => documentStore.getState().snapshot?.revision ?? null,
    scene,
    selectFaces: (faces) => {
      const scan = documentStore.getState().snapshot?.document.scan;
      if (!scan) throw new Error('no scan loaded');
      replaceSelection(scan.key, scan.faceCount, Uint32Array.from(faces));
    },
    waitForIdle: async (timeoutMs = 20_000) => {
      const deadline = Date.now() + timeoutMs;
      for (;;) {
        const busy = Object.keys(jobStore.getState().jobs).length > 0;
        const expected = documentStore.getState().snapshot?.document.scan?.faceCount ?? 0;
        if (!busy && scene().scanFaces === expected) return;
        if (Date.now() > deadline) throw new Error('application did not become idle');
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
    },
  };
  window.__m2cTest = hooks;
}
