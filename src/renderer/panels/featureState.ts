// The state a feature shows in the tree and in its properties. Some warnings only
// matter while a feature stands alone: an open net is no body, but that is what a
// later Zuschneiden expects of it. Once a later feature uses the feature, such
// warnings are dropped, and the feature shows as fine.

import type { Feature } from '@shared/protocol/generated/document-model';
import type {
  FeatureState,
  FeatureStatus,
  Issue,
} from '@shared/protocol/generated/document-results';

/** Warnings that a later feature's use of the feature answers. */
const SETTLED_BY_USE = new Set(['surfacing.openNet']);

export interface ShownStatus {
  state: FeatureState;
  issues: Issue[];
}

export function shownStatus(
  feature: Pick<Feature, 'id' | 'suppressed'>,
  status: FeatureStatus | undefined,
  used: ReadonlySet<string>,
): ShownStatus {
  if (feature.suppressed) return { state: 'suppressed', issues: status?.issues ?? [] };
  const state = status?.state ?? 'ok';
  const issues = status?.issues ?? [];
  if (!used.has(feature.id)) return { state, issues };
  const left = issues.filter((issue) => !SETTLED_BY_USE.has(issue.code));
  return { state: state === 'warning' && left.length === 0 ? 'ok' : state, issues: left };
}
