// Reading a fit feature's results from its status. The kernel reports them as
// statistics (kernel/m2c_kernel/features/types/fit.py lists the keys): quality values,
// the fitted parameters and, per applied snap, its value and measurement.

import type { TFunction } from 'i18next';

import type { FeatureStatus } from '@shared/protocol/generated/document-results';
import type { FitParams } from '@shared/protocol/generated/feature-fit';
import type { AppliedSnap, SnapId } from '@shared/protocol/generated/fitting-intent';

import type { Formatter } from '../../i18n/format';
import type { FitResultValues } from '../../tools/fit-primitive/FitResultList';
import { parallelAxis, perpendicularAxis } from '../../tools/fit-primitive/fitDraft';

type Stats = Readonly<Record<string, number | null>>;

const SNAP_IDS: readonly SnapId[] = [
  'direction',
  'offset',
  'radius',
  'halfAngle',
  'majorRadius',
  'minorRadius',
];
const AXES = ['X', 'Y', 'Z'] as const;

function number(stats: Stats, key: string): number | null {
  const value = stats[key];
  return typeof value === 'number' ? value : null;
}

/** The result block values, or null before the fit was evaluated. */
export function resultValues(status: FeatureStatus | undefined): FitResultValues | null {
  const stats: Stats = status?.stats ?? {};
  const rms = number(stats, 'rms');
  const within = number(stats, 'withinTolerance');
  const tolerance = number(stats, 'tolerance');
  if (rms === null || within === null || tolerance === null) return null;
  return {
    noise: number(stats, 'noise') ?? 0,
    rms,
    maxDeviation: number(stats, 'maxDeviation') ?? 0,
    withinTolerance: within,
    tolerance,
    passed: !status?.issues.some((issue) => issue.code === 'fit.poorFit'),
    faceCount: number(stats, 'faceCount') ?? 0,
    excludedFaces: number(stats, 'excludedFaces') ?? 0,
  };
}

/** The snaps a fit applied, rebuilt from its statistics. */
export function appliedSnaps(stats: Stats): AppliedSnap[] {
  return SNAP_IDS.flatMap((id) => {
    const value = number(stats, `snap.${id}.value`);
    const measured = number(stats, `snap.${id}.measured`);
    if (value === null || measured === null) return [];
    const target = number(stats, `snap.${id}.target`);
    const kind = id === 'direction' ? 'direction' : id === 'halfAngle' ? 'angle' : 'length';
    return [
      {
        id,
        kind,
        value,
        measured,
        uncertainty: number(stats, `snap.${id}.uncertainty`) ?? 0,
        target: target === null ? null : (AXES[target] ?? null),
      },
    ];
  });
}

export function fittedDirection(stats: Stats): readonly [number, number, number] | null {
  const values = AXES.map((axis) => number(stats, `direction${axis}`));
  return values.every((value) => value !== null) ? (values as [number, number, number]) : null;
}

/**
 * One-line summary ("⌀ 16,000 mm, parallel zu Z"): the main size of the fitted
 * shape and how its direction relates to the part axes. Falls back to the fixed
 * values while the fit has no result.
 */
export function fitSummary(
  params: FitParams,
  status: FeatureStatus | undefined,
  format: Formatter,
  t: TFunction,
): string {
  const stats: Stats = status?.stats ?? {};
  const value = (key: string, fixed: number | null) => number(stats, key) ?? fixed;
  const parts: string[] = [];
  switch (params.kind) {
    case 'plane': {
      const offset = value('offset', params.fixed.offset);
      if (offset !== null)
        parts.push(t('features:fit.summary.distance', { value: format.length(offset) }));
      break;
    }
    case 'cylinder':
    case 'sphere': {
      const radius = value('radius', params.fixed.radius);
      if (radius !== null)
        parts.push(t('features:fit.summary.diameter', { value: format.length(2 * radius) }));
      break;
    }
    case 'cone': {
      const half = value('halfAngleDeg', params.fixed.halfAngleDeg);
      if (half !== null)
        parts.push(t('features:fit.summary.angle', { value: format.angle(2 * half) }));
      break;
    }
    case 'torus': {
      const major = value('majorRadius', params.fixed.majorRadius);
      const minor = value('minorRadius', params.fixed.minorRadius);
      if (major !== null && minor !== null) {
        parts.push(
          t('features:fit.summary.radii', {
            major: format.length(major),
            minor: format.length(minor),
          }),
        );
      }
      break;
    }
  }
  const direction = fittedDirection(stats);
  if (direction && params.kind !== 'sphere') {
    // A plane whose normal is parallel to Z is perpendicular to Z, and the other way round.
    const parallel = parallelAxis(direction);
    const perpendicular = perpendicularAxis(direction);
    const plane = params.kind === 'plane';
    if (parallel)
      parts.push(
        t(`features:fit.summary.${plane ? 'perpendicular' : 'parallel'}`, { axis: parallel }),
      );
    else if (perpendicular) {
      parts.push(
        t(`features:fit.summary.${plane ? 'parallel' : 'perpendicular'}`, { axis: perpendicular }),
      );
    }
  }
  return parts.join(', ');
}
