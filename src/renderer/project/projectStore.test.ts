import { describe, expect, it } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { isLoadResult } from './loadResult';
import { hasUnsavedChanges, projectName, windowTitle } from './projectStore';

function snapshot(revision: number, scanFile: string | null): DocumentSnapshot {
  const scan = scanFile === null ? null : { source: { fileName: scanFile } };
  return { revision, document: { scan } } as unknown as DocumentSnapshot;
}

describe('project state', () => {
  it('has unsaved changes only with a scan whose revision was not saved', () => {
    const saved = { fileName: 'halterung.m2c', savedRevision: 7 };
    expect(hasUnsavedChanges(snapshot(7, 'scan.stl'), saved)).toBe(false);
    expect(hasUnsavedChanges(snapshot(8, 'scan.stl'), saved)).toBe(true);
    expect(hasUnsavedChanges(snapshot(9, null), saved)).toBe(false);
    expect(
      hasUnsavedChanges(snapshot(1, 'scan.stl'), { fileName: null, savedRevision: null }),
    ).toBe(true);
    expect(hasUnsavedChanges(null, saved)).toBe(false);
  });

  it('names the project after its file, else after the scan', () => {
    const untitled = { fileName: null, savedRevision: null };
    expect(projectName(snapshot(1, 'halterung_scan.stl'), untitled)).toBe('halterung_scan');
    expect(
      projectName(snapshot(1, 'scan.stl'), { fileName: 'flansch.m2c', savedRevision: 1 }),
    ).toBe('flansch');
    expect(projectName(snapshot(0, null), untitled)).toBeNull();
    expect(projectName(snapshot(1, '.hidden'), untitled)).toBe('.hidden');
  });

  it('builds the window title with a star for unsaved changes', () => {
    expect(windowTitle('halterung', true)).toBe('halterung* - Mesh-to-CAD');
    expect(windowTitle('halterung', false)).toBe('halterung - Mesh-to-CAD');
    expect(windowTitle(null, false)).toBe('Mesh-to-CAD');
  });

  it('tells a loaded project from an import report', () => {
    expect(isLoadResult({ fileName: 'a.m2c', revision: 3, ui: null })).toBe(true);
    expect(isLoadResult({ fileName: 'a.stl', pendingId: 'x', faceCount: 1 })).toBe(false);
    expect(isLoadResult(null)).toBe(false);
  });
});
