// The user adjustments applied after an alignment (ARCHITECTURE.md 4.4): turn the
// part over, reverse X and Y, rotate in quarter turns about Z. The kernel applies
// them in this order: turn over, reverse, then the quarter turns.

import type { AlignmentAdjust } from '@shared/protocol/generated/document-model';

export const NO_ADJUST: AlignmentAdjust = { flipX: false, flipZ: false, rotateZ90: 0 };

export type AdjustAction = 'flipZ' | 'flipX' | 'rotate';

export function applyAdjust(adjust: AlignmentAdjust, action: AdjustAction): AlignmentAdjust {
  switch (action) {
    case 'flipZ':
      return { ...adjust, flipZ: !adjust.flipZ };
    case 'flipX':
      return { ...adjust, flipX: !adjust.flipX };
    case 'rotate':
      return { ...adjust, rotateZ90: (normalisedQuarters(adjust.rotateZ90) + 1) % 4 };
  }
}

/** Quarter turns in 0..3, also for values stored outside that range. */
export function normalisedQuarters(quarters: number): number {
  return ((Math.round(quarters) % 4) + 4) % 4;
}

export function rotationDegrees(adjust: AlignmentAdjust): number {
  return normalisedQuarters(adjust.rotateZ90) * 90;
}

export function isAdjusted(adjust: AlignmentAdjust): boolean {
  return adjust.flipX || adjust.flipZ || normalisedQuarters(adjust.rotateZ90) !== 0;
}

export function sameAdjust(a: AlignmentAdjust, b: AlignmentAdjust): boolean {
  return (
    a.flipX === b.flipX &&
    a.flipZ === b.flipZ &&
    normalisedQuarters(a.rotateZ90) === normalisedQuarters(b.rotateZ90)
  );
}
