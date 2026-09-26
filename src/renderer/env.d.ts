/// <reference types="vite/client" />

import type { M2CBridge } from '@shared/bridge';

declare global {
  interface Window {
    readonly m2c: M2CBridge;
  }
}

export {};
