import type { M2CBridge } from '@shared/bridge';

// The preload bridge as seen from `page.evaluate` in the e2e specs (the renderer declares
// the same property in src/renderer/env.d.ts, which tsconfig.node.json does not include).
declare global {
  interface Window {
    readonly m2c: M2CBridge;
  }
}

export {};
