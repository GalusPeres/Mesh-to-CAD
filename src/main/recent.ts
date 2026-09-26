import type { RecentFile } from '@shared/bridge';

/**
 * Recently opened meshes and projects (at most 10). The renderer only ever sees
 * opaque ids; the paths stay in the main process.
 *
 * Not implemented yet: the list is always empty.
 */
export class RecentFiles {
  list(): RecentFile[] {
    return [];
  }

  /** Path of a recent entry, or null if the id is unknown. */
  resolve(_recentId: string): string | null {
    return null;
  }

  remember(_filePath: string, _kind: RecentFile['kind']): void {
    // Recorded once the recent-files list is implemented.
  }
}
