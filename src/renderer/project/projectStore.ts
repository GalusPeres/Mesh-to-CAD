import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { useDocument } from '../state/documentStore';

/**
 * The project file the document belongs to, as far as the renderer knows it.
 * Paths stay in the main process; the renderer keeps only the file name and the
 * revision that was last saved or opened, which is enough for the window title
 * and for unsaved-change checks.
 */
export interface ProjectState {
  /** File name of the project (`halterung.m2c`), or null for a project never saved. */
  fileName: string | null;
  /** Revision stored in that file; the document is unchanged while it is the head. */
  savedRevision: number | null;
}

export const projectStore = createStore<ProjectState>(() => ({
  fileName: null,
  savedRevision: null,
}));

export function useProject<T>(selector: (state: ProjectState) => T): T {
  return useStore(projectStore, selector);
}

/** The document was written to or read from a project file. */
export function markSaved(fileName: string, revision: number): void {
  projectStore.setState({ fileName, savedRevision: revision });
}

/** The document no longer belongs to a file (new project, imported scan, recovery). */
export function markUntitled(): void {
  projectStore.setState({ fileName: null, savedRevision: null });
}

export const APP_TITLE = 'Mesh-to-CAD';

/**
 * Unsaved changes exist when the document holds a scan and its revision is not
 * the saved one. Undoing back to the saved revision makes the project clean
 * again; an empty document has nothing to lose.
 */
export function hasUnsavedChanges(
  snapshot: DocumentSnapshot | null,
  project: ProjectState,
): boolean {
  if (!snapshot?.document.scan) return false;
  return snapshot.revision !== project.savedRevision;
}

/** Name shown in the title and dialogs: the project file, else the scan, without extension. */
export function projectName(
  snapshot: DocumentSnapshot | null,
  project: ProjectState,
): string | null {
  const file = project.fileName ?? snapshot?.document.scan?.source.fileName ?? null;
  return file === null ? null : withoutExtension(file);
}

/** Window title: `<name>* - Mesh-to-CAD` with unsaved changes, `<name> - Mesh-to-CAD` without. */
export function windowTitle(name: string | null, unsaved: boolean): string {
  if (name === null) return APP_TITLE;
  return `${name}${unsaved ? '*' : ''} - ${APP_TITLE}`;
}

export function withoutExtension(fileName: string): string {
  const dot = fileName.lastIndexOf('.');
  return dot > 0 ? fileName.slice(0, dot) : fileName;
}

export function currentProjectState(snapshot: DocumentSnapshot | null): {
  name: string | null;
  unsaved: boolean;
} {
  const project = projectStore.getState();
  return {
    name: projectName(snapshot, project),
    unsaved: hasUnsavedChanges(snapshot, project),
  };
}

/** Name and unsaved flag of the current project, for components. */
export function useProjectStatus(): { name: string | null; unsaved: boolean } {
  const snapshot = useDocument((state) => state.snapshot);
  const project = useProject((state) => state);
  return { name: projectName(snapshot, project), unsaved: hasUnsavedChanges(snapshot, project) };
}
