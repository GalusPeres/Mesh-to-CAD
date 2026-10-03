// The units the sketch panel lists and labels: recognised shapes (a button), free
// profiles (lines and arcs joined by shared points, such as a split outline) and
// single entities. A group id is the shape id, `k<n>` for a free profile (after its
// first entity) or the entity id.

import type { SketchParams, SketchShape } from '@shared/protocol/generated/sketch-params';

export interface SketchGroup {
  id: string;
  kind: 'shape' | 'profile' | 'entity';
  entities: readonly string[];
  shape?: SketchShape;
}

function profiles(sketch: SketchParams, free: readonly string[]): string[][] {
  const parent = new Map(free.map((id) => [id, id]));
  const find = (id: string): string => {
    let root = id;
    while (parent.get(root) !== root) root = parent.get(root) ?? root;
    parent.set(id, root);
    return root;
  };
  const byPoint = new Map<string, string[]>();
  for (const entity of sketch.entities) {
    if (entity.type === 'circle' || !parent.has(entity.id)) continue;
    for (const point of [entity.start, entity.end]) {
      byPoint.set(point, [...(byPoint.get(point) ?? []), entity.id]);
    }
  }
  for (const ids of byPoint.values()) {
    for (const other of ids.slice(1)) parent.set(find(other), find(ids[0] as string));
  }
  const groups = new Map<string, string[]>();
  for (const id of free) groups.set(find(id), [...(groups.get(find(id)) ?? []), id]);
  return [...groups.values()];
}

export function sketchGroups(sketch: SketchParams): SketchGroup[] {
  const inShapes = new Set(sketch.shapes.flatMap((shape) => shape.entities));
  const free = sketch.entities.map((entity) => entity.id).filter((id) => !inShapes.has(id));
  return [
    ...sketch.shapes.map((shape): SketchGroup => ({
      id: shape.id,
      kind: 'shape',
      entities: shape.entities,
      shape,
    })),
    ...profiles(sketch, free).map((ids): SketchGroup =>
      ids.length > 1
        ? { id: `k${(ids[0] as string).slice(1)}`, kind: 'profile', entities: ids }
        : { id: ids[0] as string, kind: 'entity', entities: ids },
    ),
  ];
}

/** The group an entity or group id belongs to. */
export function groupOf(groups: readonly SketchGroup[], id: string | null): SketchGroup | null {
  if (!id) return null;
  return groups.find((group) => group.id === id || group.entities.includes(id)) ?? null;
}

/** The entities a selection stands for: a whole group, or one entity of a group. */
export function selectedEntities(groups: readonly SketchGroup[], id: string | null): string[] {
  const group = groupOf(groups, id);
  if (!group || !id) return [];
  return group.id === id ? [...group.entities] : [id];
}
