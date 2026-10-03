// The plane step: which features can carry a sketch plane or an axis, and how
// the panel's plane choice maps to the stored section.

import type { Feature } from '@shared/protocol/generated/document-model';
import type { SketchParams, SketchSection } from '@shared/protocol/generated/sketch-params';

export type PlaneKind = 'XY' | 'YZ' | 'XZ' | 'feature' | 'axisNormal' | 'rotational';
export const PLANE_KINDS: readonly PlaneKind[] = [
  'XY',
  'YZ',
  'XZ',
  'feature',
  'axisNormal',
  'rotational',
];
export const GLOBAL_AXES = ['X', 'Y', 'Z'] as const;

/**
 * Default cut above a plane fitted to a scan face (mm along its normal): a cut right
 * at the face meets only the face's noise; just above it cuts raised shapes such as
 * buttons cleanly.
 */
export const FACE_CUT_MM = 0.5;

const STANDARD_NORMALS: Record<'XY' | 'YZ' | 'XZ', readonly [number, number, number]> = {
  XY: [0, 0, 1],
  YZ: [1, 0, 0],
  XZ: [0, -1, 0],
};

interface Params {
  kind?: string;
  definition?: { type?: string };
}

function paramsOf(feature: Feature): Params {
  return (feature.params ?? {}) as Params;
}

/** Fits of kind plane and reference planes: they give a sketch plane. */
export function providesPlane(feature: Feature): boolean {
  const params = paramsOf(feature);
  if (feature.type === 'fit') return params.kind === 'plane';
  if (feature.type === 'reference') return params.definition?.type !== 'axisFromPlanes';
  return false;
}

/** Cylinder, cone and torus fits and reference axes: they give an axis. */
export function providesAxis(feature: Feature): boolean {
  const params = paramsOf(feature);
  if (feature.type === 'fit') return ['cylinder', 'cone', 'torus'].includes(params.kind ?? '');
  if (feature.type === 'reference') return params.definition?.type === 'axisFromPlanes';
  return false;
}

/** Features before `until` (the edited sketch) that are not suppressed. */
export function usableFeatures(features: readonly Feature[], until: string | null): Feature[] {
  const end = until ? features.findIndex((feature) => feature.id === until) : -1;
  return (end >= 0 ? features.slice(0, end) : features).filter((feature) => !feature.suppressed);
}

export function planeKindOf(section: SketchSection): PlaneKind {
  if (section.type === 'rotational') return 'rotational';
  if (section.plane.type === 'standard') return section.plane.plane;
  return section.plane.type;
}

/** Where the cut starts on a feature plane: above a fitted scan face, else on the plane. */
export function featureCut(feature: Feature | undefined): number {
  return feature?.type === 'fit' ? FACE_CUT_MM : 0;
}

/** The section on a feature plane, cut at its default position. */
export function featureSection(feature: Feature): SketchSection {
  return {
    type: 'planar',
    plane: { type: 'feature', feature: feature.id },
    offset: 0,
    sectionOffset: featureCut(feature),
    xDirection: null,
    flip: false,
  };
}

/** The section for a newly chosen plane kind; offsets reset, the cut goes through `center`. */
export function sectionFor(
  kind: PlaneKind,
  previous: SketchSection,
  choices: { plane: string | null; axis: string; planeCut?: number },
  center: readonly [number, number, number] | null,
): SketchSection {
  if (kind === 'rotational') return { type: 'rotational', axis: choices.axis, angleDeg: 0 };
  const base = { type: 'planar' as const, offset: 0, xDirection: null, flip: false };
  if (kind === 'feature') {
    return {
      ...base,
      plane: { type: 'feature', feature: choices.plane ?? '' },
      sectionOffset: choices.planeCut ?? 0,
    };
  }
  if (kind === 'axisNormal') {
    return { ...base, plane: { type: 'axisNormal', axis: choices.axis }, sectionOffset: 0 };
  }
  const normal = STANDARD_NORMALS[kind];
  const cut = center ? center[0] * normal[0] + center[1] * normal[1] + center[2] * normal[2] : 0;
  const keep =
    previous.type === 'planar' &&
    previous.plane.type === 'standard' &&
    previous.plane.plane === kind;
  return {
    ...base,
    plane: { type: 'standard', plane: kind },
    sectionOffset: keep ? previous.sectionOffset : Math.round(cut * 1000) / 1000,
  };
}

/** A sketch without geometry on the given section. */
export function emptySketch(section: SketchSection): SketchParams {
  return {
    section,
    tolerance: null,
    noise: null,
    points: [],
    entities: [],
    constraints: [],
    snaps: [],
    dimensions: [],
    rejectedSnaps: [],
    shapes: [],
  };
}

/** Scan centre in part coordinates (the scan origin is close to its centroid). */
export function scanCenter(
  scan: { origin: readonly number[]; transform: readonly number[] } | null | undefined,
): [number, number, number] | null {
  if (!scan) return null;
  const [x = 0, y = 0, z = 0] = scan.origin;
  const m = scan.transform;
  const row = (i: number) =>
    (m[4 * i] ?? 0) * x + (m[4 * i + 1] ?? 0) * y + (m[4 * i + 2] ?? 0) * z + (m[4 * i + 3] ?? 0);
  return [row(0), row(1), row(2)];
}
