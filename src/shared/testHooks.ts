// Hooks the renderer installs for end-to-end tests (only with M2C_E2E=1).
// Shared so the renderer and the Playwright tests agree on one declaration.

export interface TestHooks {
  /** Revision of the mirrored document, or null before the kernel answered. */
  revision(): number | null;
  /** Counts of what the viewport draws. */
  scene(): { scanFaces: number; items: number };
  /** Replace the working selection with these faces of the current scan. */
  selectFaces(faces: readonly number[]): void;
  /** Resolves when no kernel request runs and the viewport shows the current scan. */
  waitForIdle(timeoutMs?: number): Promise<void>;
}

declare global {
  interface Window {
    __m2cTest?: TestHooks;
  }
}
