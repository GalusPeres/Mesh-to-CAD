import type { LoadResult } from '@shared/protocol/generated/project';

/** The result of `project.load` (a project from the dialog, the recent list or a drop). */
export function isLoadResult(value: unknown): value is LoadResult {
  if (typeof value !== 'object' || value === null) return false;
  const result = value as Record<string, unknown>;
  return (
    typeof result.fileName === 'string' &&
    typeof result.revision === 'number' &&
    'ui' in result &&
    !('pendingId' in result)
  );
}
