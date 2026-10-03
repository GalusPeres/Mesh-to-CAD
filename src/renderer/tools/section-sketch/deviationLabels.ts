// Live 2D deviation in the view: the largest distance of the section points from
// each entity. A shape (a button) or a free profile carries one label with its worst
// entity; the group under the pointer, the selected one and single entities show
// one label per entity.

import type { EntityFitInfo } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { entityPolyline } from './draftGeometry';
import { sketchGroups } from './sketchGroups';
import type { Vec2 } from './sketchMath';

export interface DeviationLabel {
  at: Vec2;
  /** Largest distance in mm. */
  value: number;
  passed: boolean | null;
}

function middle(points: readonly Vec2[]): Vec2 | null {
  return points[Math.floor((points.length - 1) / 2)] ?? null;
}

/** The highest point of the outline (the middle of a flat top), so the label sits on it. */
function top(points: readonly Vec2[]): Vec2 | null {
  if (!points.length) return null;
  const highest = Math.max(...points.map((p) => p[1]));
  const level = points.filter((p) => p[1] >= highest - 1e-3 * (1 + Math.abs(highest)));
  const xs = level.map((p) => p[0]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, highest];
}

export function deviationLabels(
  sketch: SketchParams,
  fits: readonly EntityFitInfo[],
  expanded: readonly string[],
): DeviationLabel[] {
  const byEntity = new Map(fits.map((fit) => [fit.entity, fit]));
  const labels: DeviationLabel[] = [];
  for (const group of sketchGroups(sketch)) {
    const judged = group.entities
      .map((id) => ({ id, fit: byEntity.get(id) }))
      .filter((item) => item.fit?.maxDistance != null);
    if (group.kind === 'entity' || expanded.includes(group.id)) {
      for (const { id, fit } of judged) {
        const at = middle(entityPolyline(sketch, id));
        if (at) labels.push({ at, value: fit?.maxDistance ?? 0, passed: fit?.passed ?? null });
      }
      continue;
    }
    const at = top(group.entities.flatMap((id) => entityPolyline(sketch, id)));
    if (!judged.length || !at) continue;
    labels.push({
      at,
      value: Math.max(...judged.map(({ fit }) => fit?.maxDistance ?? 0)),
      passed: judged.every(({ fit }) => fit?.passed !== false),
    });
  }
  return labels;
}
