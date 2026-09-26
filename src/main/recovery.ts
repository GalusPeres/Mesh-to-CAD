import {
  closeSync,
  openSync,
  readFileSync,
  readSync,
  readdirSync,
  rmSync,
  statSync,
} from 'node:fs';
import path from 'node:path';

import type { RecoveryCandidate } from '@shared/bridge';

/** Sessions of crashed instances older than this are deleted instead of offered. */
export const MAX_SESSION_AGE_MS = 7 * 24 * 60 * 60 * 1000;

const LOCK_FILE = 'session.lock';
const INFO_FILE = 'session.json';
const HEAD_FILE = 'head.json';

export interface RecoveryOptions {
  now?: number;
  isLocked?: (directory: string) => boolean;
}

/**
 * Session directories left behind by a crashed instance: their `session.lock` is
 * free and their checked-out revision holds a scan. They are offered for restore
 * at start, newest first, labelled with the scan's file name. Sessions older than
 * seven days and sessions whose checked-out document is empty are deleted.
 *
 * The candidate id is the directory name inside the sessions directory.
 */
export function findRecoveryCandidates(
  sessionsDirectory: string,
  currentSession: string,
  options: RecoveryOptions = {},
): RecoveryCandidate[] {
  const now = options.now ?? Date.now();
  const isLocked = options.isLocked ?? isSessionLocked;
  let names: string[];
  try {
    names = readdirSync(sessionsDirectory, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
  } catch {
    return [];
  }
  const current = path.resolve(currentSession);
  const candidates: RecoveryCandidate[] = [];
  for (const name of names) {
    const directory = path.join(sessionsDirectory, name);
    if (path.resolve(directory) === current || isLocked(directory)) continue;
    const startedAt = sessionStart(directory, name);
    const scanName = headScanName(directory);
    if (now - startedAt > MAX_SESSION_AGE_MS || scanName === null) {
      tryDeleteSession(directory);
      continue;
    }
    candidates.push({ id: name, startedAt, label: scanName });
  }
  return candidates.sort((a, b) => b.startedAt - a.startedAt);
}

/**
 * True while a kernel holds the session lock. The kernel locks the first byte of
 * `session.lock` (`msvcrt.locking`); reading that byte from another process then
 * fails with EBUSY. Unexpected errors count as locked, so a session is never
 * touched while it might be in use.
 */
export function isSessionLocked(directory: string): boolean {
  let handle: number;
  try {
    handle = openSync(path.join(directory, LOCK_FILE), 'r');
  } catch (error) {
    return (error as NodeJS.ErrnoException).code !== 'ENOENT';
  }
  try {
    readSync(handle, Buffer.alloc(1), 0, 1, 0);
    return false;
  } catch {
    return true;
  } finally {
    closeSync(handle);
  }
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

function tryDeleteSession(directory: string): void {
  try {
    deleteSession(directory);
  } catch {
    // Still held by a scanner or indexer; the next start tries again.
  }
}

/** Start time in ms: `session.json` of the kernel, else the `<ms>-<pid>` name, else mtime. */
function sessionStart(directory: string, name: string): number {
  const info = readJson(path.join(directory, INFO_FILE));
  if (isRecord(info) && typeof info.started === 'number') return info.started * 1000;
  const fromName = /^(\d{12,})-\d+$/.exec(name);
  if (fromName) return Number(fromName[1]);
  try {
    return statSync(directory).mtimeMs;
  } catch {
    return 0;
  }
}

/**
 * File name of the scan in the checked-out revision, or null when that revision
 * has no scan (nothing to restore) or cannot be read.
 */
function headScanName(directory: string): string | null {
  const head = readJson(path.join(directory, HEAD_FILE));
  if (!isRecord(head) || typeof head.head !== 'number') return null;
  const revision = readJson(path.join(directory, 'revisions', `${head.head}.json`));
  const fileName = dig(revision, ['document', 'document', 'scan', 'source', 'fileName']);
  return typeof fileName === 'string' ? fileName : null;
}

function readJson(file: string): unknown {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function dig(value: unknown, keys: readonly string[]): unknown {
  return keys.reduce<unknown>((node, key) => (isRecord(node) ? node[key] : undefined), value);
}
