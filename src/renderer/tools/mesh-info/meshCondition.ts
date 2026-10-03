import type { MeshReport } from '@shared/protocol/generated/mesh';

/** Defects that *Reparieren* removes: faces without area, duplicates, flipped faces. */
export function repairableDefects(report: MeshReport): boolean {
  return report.degenerateFaces + report.duplicateFaces + report.inconsistentEdges > 0;
}
