import type { RepairStep } from '@shared/protocol/generated/mesh-repair';

/** The repair steps in the order the kernel runs them, with the count each one reports. */
export const REPAIR_STEPS: readonly { step: RepairStep; count: string }[] = [
  { step: 'weld', count: 'mergedVertices' },
  { step: 'degenerate', count: 'degenerateFaces' },
  { step: 'duplicates', count: 'duplicateFaces' },
  { step: 'winding', count: 'flippedFaces' },
  { step: 'orientation', count: 'invertedParts' },
];

/** Switch one step on or off; the result keeps the kernel's order. */
export function toggleStep(
  selected: readonly RepairStep[],
  step: RepairStep,
  on: boolean,
): RepairStep[] {
  return REPAIR_STEPS.map((item) => item.step).filter((item) =>
    item === step ? on : selected.includes(item),
  );
}
