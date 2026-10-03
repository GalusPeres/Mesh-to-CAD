import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import type { RecentFile } from '@shared/bridge';

import { settingsPath } from './paths';

export const MAX_RECENT_FILES = 10;

interface StoredEntry {
  id: string;
  path: string;
  kind: RecentFile['kind'];
  openedAt: number;
}

/** `recent.json` next to `settings.json` in the roaming app data. */
export function recentFilesPath(): string {
  return path.join(path.dirname(settingsPath()), 'recent.json');
}

/**
 * Recently opened scans and projects, newest first, at most ten. The renderer
 * only ever sees opaque ids, file names and folders; opening an entry goes
 * through `resolve`, so the path never comes from the renderer.
 */
export class RecentFiles {
  private entries: StoredEntry[] | null = null;

  constructor(
    private readonly file: string = recentFilesPath(),
    private readonly now: () => number = Date.now,
  ) {}

  /** The entries whose files still exist; entries of missing files are dropped. */
  list(): RecentFile[] {
    const entries = this.load();
    const present = entries.filter((entry) => existsSync(entry.path));
    if (present.length !== entries.length) this.store(present);
    return present.map((entry) => ({
      id: entry.id,
      name: path.basename(entry.path),
      folder: path.dirname(entry.path),
      kind: entry.kind,
      openedAt: entry.openedAt,
    }));
  }

  /** Path of a recent entry, or null if the id is unknown. */
  resolve(recentId: string): string | null {
    return this.load().find((entry) => entry.id === recentId)?.path ?? null;
  }

  /** Put a file at the top of the list (keeping its id if it was there already). */
  remember(filePath: string, kind: RecentFile['kind']): void {
    const key = comparable(filePath);
    const entries = this.load();
    const existing = entries.find((entry) => comparable(entry.path) === key);
    const entry: StoredEntry = {
      id: existing?.id ?? randomUUID(),
      path: path.resolve(filePath),
      kind,
      openedAt: this.now(),
    };
    const others = entries.filter((candidate) => comparable(candidate.path) !== key);
    this.store([entry, ...others].slice(0, MAX_RECENT_FILES));
  }

  private load(): StoredEntry[] {
    this.entries ??= readEntries(this.file);
    return this.entries;
  }

  private store(entries: StoredEntry[]): void {
    this.entries = entries;
    try {
      mkdirSync(path.dirname(this.file), { recursive: true });
      const temporary = `${this.file}.${process.pid}.tmp`;
      writeFileSync(temporary, JSON.stringify(entries, null, 2), 'utf8');
      renameSync(temporary, this.file);
    } catch {
      // The list is a convenience: failing to persist it must not fail opening a file.
    }
  }
}

/** Windows paths compare case-insensitively. */
function comparable(filePath: string): string {
  const resolved = path.resolve(filePath);
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
}

function readEntries(file: string): StoredEntry[] {
  let data: unknown;
  try {
    data = JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  return data.filter(isStoredEntry).slice(0, MAX_RECENT_FILES);
}

function isStoredEntry(value: unknown): value is StoredEntry {
  if (typeof value !== 'object' || value === null) return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.id === 'string' &&
    typeof entry.path === 'string' &&
    path.isAbsolute(entry.path) &&
    (entry.kind === 'mesh' || entry.kind === 'project') &&
    typeof entry.openedAt === 'number'
  );
}
