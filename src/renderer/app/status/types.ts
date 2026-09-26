import type { ComponentType } from 'react';

/**
 * An item on the right side of the status bar, discovered from `*.status.tsx`.
 * Orders: selection 10, triangles 20, tolerance 30, deviation 40, kernel 50.
 * A component that has nothing to say renders null.
 */
export interface StatusItem {
  order: number;
  Component: ComponentType;
}
