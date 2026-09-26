// Registries for UI pieces that other modules contribute to the shell, so the
// shell never imports them by name:
//
//   *.dialog.tsx   export const dialog: ComponentType    (mounted once; manages its own state)
//   *.overlay.tsx  export const overlay: ViewportOverlay (drawn over the viewport)

import type { ComponentType } from 'react';

export interface ViewportOverlay {
  /** Corner of the viewport; overlays never overlap each other. */
  anchor: 'top-left' | 'top-right' | 'right' | 'bottom-left';
  order: number;
  Component: ComponentType;
}

const dialogModules = import.meta.glob<{ dialog: ComponentType }>('../**/*.dialog.tsx', {
  eager: true,
});
const overlayModules = import.meta.glob<{ overlay: ViewportOverlay }>('../**/*.overlay.tsx', {
  eager: true,
});

export const DIALOGS: readonly ComponentType[] = Object.values(dialogModules).map(
  (module) => module.dialog,
);

export const OVERLAYS: readonly ViewportOverlay[] = Object.values(overlayModules)
  .map((module) => module.overlay)
  .sort((a, b) => a.order - b.order);
