// Texts of the sketch tool: entity rows, constraints, snaps, the profile state
// and the plane caption. Strings come from `tools:sectionSketch.*`.

import type { TFunction } from 'i18next';

import type { ProfileState } from '@shared/protocol/generated/sketch';
import type {
  SketchConstraint,
  SketchEntity,
  SketchParams,
  SketchSection,
  SketchSnap,
} from '@shared/protocol/generated/sketch-params';

import type { Formatter } from '../../i18n/format';
import type { SnapListItem } from '../../ui/SnapList/SnapList';
import { pointOf, xy } from './draftGeometry';
import { lineLength } from './sketchMath';

const KEY = 'tools:sectionSketch';

/** Line length, arc radius or circle diameter of an entity, formatted. */
export function entitySize(sketch: SketchParams, entity: SketchEntity, format: Formatter): string {
  if (entity.type === 'line') {
    return format.length(
      lineLength(xy(pointOf(sketch, entity.start)), xy(pointOf(sketch, entity.end))),
    );
  }
  if (entity.type === 'arc') return `R ${format.length(entity.radius)}`;
  return `⌀ ${format.length(2 * entity.radius)}`;
}

export function entityName(entity: SketchEntity, t: TFunction): string {
  const kind = entity.type === 'line' && entity.origin === 'axis' ? 'axisLine' : entity.type;
  return t(`${KEY}.entity.${kind}`);
}

/** "Profil geschlossen: 3 Konturen" / "Profil offen: 2 Lücken" / "Keine Elemente". */
export function profileText(
  profile: ProfileState | null,
  entityCount: number,
  t: TFunction,
): string {
  if (!profile || entityCount === 0) return t(`${KEY}.profile.empty`);
  if (profile.branchPoints.length) return t(`${KEY}.profile.branched`);
  if (profile.closed) return t(`${KEY}.profile.closed`, { count: profile.loops.length });
  return t(`${KEY}.profile.open`, { count: profile.gaps.length });
}

export function profileSeverity(profile: ProfileState | null): 'info' | 'warning' {
  return profile && (profile.closed || profile.gaps.length === 0) && !profile.branchPoints.length
    ? 'info'
    : 'warning';
}

export function constraintText(
  constraint: SketchConstraint,
  labels: ReadonlyMap<string, string>,
  t: TFunction,
): string {
  const refs = constraint.refs.map((ref) => labels.get(ref) ?? ref).join(', ');
  return `${t(`${KEY}.constraint.${constraint.kind}`)}: ${refs}`;
}

export function snapItem(
  snap: SketchSnap,
  labels: ReadonlyMap<string, string>,
  format: Formatter,
  t: TFunction,
): SnapListItem {
  const owner = labels.get(snap.entity) ?? snap.entity;
  if (snap.kind === 'angle') {
    return {
      id: snap.id,
      text: t(`${KEY}.snap.angle`, { entity: owner, value: format.angle(snap.value) }),
      measured: `${format.number(snap.measured, 2)} ± ${format.number(snap.uncertainty, 2)}`,
    };
  }
  if (snap.kind === 'boltCircle') {
    return {
      id: snap.id,
      text: t(`${KEY}.snap.boltCircle`, {
        value: format.length(snap.value),
        count: snap.members.length,
        pitch: format.angle(snap.pitchDeg ?? 0),
      }),
      measured: `${format.number(snap.measured, 3)} ± ${format.number(snap.uncertainty, 3)}`,
    };
  }
  return {
    id: snap.id,
    text: t(`${KEY}.snap.${snap.kind}`, { entity: owner, value: format.length(snap.value) }),
    measured: `${format.number(snap.measured, 3)} ± ${format.number(snap.uncertainty, 3)}`,
  };
}

/** Short names of the entities for lists and constraints: "Linie 3", "Bogen 7". */
export function entityLabels(sketch: SketchParams, t: TFunction): Map<string, string> {
  return new Map(
    sketch.entities.map((entity) => [entity.id, `${entityName(entity, t)} ${entity.id.slice(1)}`]),
  );
}

/** Where the sketch lies: "Ebene XY + 5,000 mm", "Drehprofil um Z" (caption and panel). */
export function sectionText(
  section: SketchSection,
  featureNames: ReadonlyMap<string, string>,
  format: Formatter,
  t: TFunction,
): string {
  if (section.type === 'rotational') {
    return t(`${KEY}.caption.rotational`, { axis: featureNames.get(section.axis) ?? section.axis });
  }
  const source = section.plane;
  const plane =
    source.type === 'standard'
      ? t(`${KEY}.caption.standard`, { plane: source.plane })
      : source.type === 'feature'
        ? (featureNames.get(source.feature) ?? source.feature)
        : t(`${KEY}.caption.axisNormal`, { axis: featureNames.get(source.axis) ?? source.axis });
  const offset = section.offset;
  if (Math.abs(offset) < 5e-4) return plane;
  return `${plane} ${offset < 0 ? '−' : '+'} ${format.length(Math.abs(offset))}`;
}
