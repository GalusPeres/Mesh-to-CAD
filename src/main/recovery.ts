import { rmSync } from 'node:fs';
import path from 'node:path';

import type { RecoveryCandidate } from '@shared/bridge';

/**
 * Session directories left behind by a crashed instance: their `session.lock` is
 * free and they hold at least one committed revision. They are offered for restore
 * at start; sessions older than seven days are deleted instead.
 *
 * The candidate id is the directory name inside the sessions directory.
 *
 * Not implemented yet: no candidates are reported.
 */
export function findRecoveryCandidates(
  _sessionsDirectory: string,
  _currentSession: string,
): RecoveryCandidate[] {
  return [];
}

/** Directory of a candidate, or null if the id does not name a current candidate. */
export function candidateDirectory(
  sessionsDirectory: string,
  candidates: readonly RecoveryCandidate[],
  candidateId: string,
): string | null {
  if (!candidates.some((candidate) => candidate.id === candidateId)) return null;
  const directory = path.resolve(sessionsDirectory, path.basename(candidateId));
  return path.dirname(directory) === path.resolve(sessionsDirectory) ? directory : null;
}

/** Delete a session directory; retries because antivirus scanners hold files briefly. */
export function deleteSession(directory: string): void {
  rmSync(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
