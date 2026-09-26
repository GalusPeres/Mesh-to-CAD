import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MAX_RECENT_FILES, RecentFiles } from './recent';

vi.mock('electron', () => ({ app: { getPath: () => tmpdir(), isPackaged: false } }));

let folder: string;
let store: string;

function touch(name: string): string {
  const file = path.join(folder, name);
  writeFileSync(file, 'x');
  return file;
}

beforeEach(() => {
  folder = mkdtempSync(path.join(tmpdir(), 'm2c-recent-'));
  store = path.join(folder, 'app', 'recent.json');
});

afterEach(() => {
  rmSync(folder, { recursive: true, force: true });
});

describe('RecentFiles', () => {
  it('lists the newest file first with name and folder, and resolves its id', () => {
    let clock = 1000;
    const recent = new RecentFiles(store, () => clock++);
    const scan = touch('halterung.stl');
    const project = touch('halterung.m2c');
    recent.remember(scan, 'mesh');
    recent.remember(project, 'project');

    const listed = recent.list();
    expect(listed.map((entry) => [entry.name, entry.kind])).toEqual([
      ['halterung.m2c', 'project'],
      ['halterung.stl', 'mesh'],
    ]);
    expect(listed[0]?.folder).toBe(folder);
    expect(listed[0]?.openedAt).toBe(1001);
    expect(recent.resolve(listed[1]?.id ?? '')).toBe(scan);
    expect(recent.resolve('unknown')).toBeNull();
  });

  it('keeps the id of a file opened again and moves it to the top', () => {
    const recent = new RecentFiles(store);
    const first = touch('a.stl');
    recent.remember(first, 'mesh');
    const id = recent.list()[0]?.id;
    recent.remember(touch('b.stl'), 'mesh');
    recent.remember(first.toUpperCase(), 'mesh');
    const listed = recent.list();
    expect(listed).toHaveLength(2);
    expect(listed[0]?.id).toBe(id);
  });

  it('keeps at most ten entries', () => {
    const recent = new RecentFiles(store);
    for (let index = 0; index < MAX_RECENT_FILES + 3; index += 1) {
      recent.remember(touch(`scan-${index}.stl`), 'mesh');
    }
    const names = recent.list().map((entry) => entry.name);
    expect(names).toHaveLength(MAX_RECENT_FILES);
    expect(names[0]).toBe('scan-12.stl');
    expect(names).not.toContain('scan-2.stl');
  });

  it('drops files that no longer exist and persists the list', () => {
    const recent = new RecentFiles(store);
    const kept = touch('kept.m2c');
    const removed = touch('removed.m2c');
    recent.remember(removed, 'project');
    recent.remember(kept, 'project');
    rmSync(removed);
    expect(recent.list().map((entry) => entry.name)).toEqual(['kept.m2c']);

    const reopened = new RecentFiles(store);
    expect(reopened.list().map((entry) => entry.name)).toEqual(['kept.m2c']);
    const stored = JSON.parse(readFileSync(store, 'utf8')) as unknown[];
    expect(stored).toHaveLength(1);
  });

  it('ignores a damaged or hand-edited list', () => {
    writeFileSync(path.join(folder, 'bad.json'), '{"not": "a list"}');
    expect(new RecentFiles(path.join(folder, 'bad.json')).list()).toEqual([]);
    const entries = [
      { id: 'x', path: 'relative.stl', kind: 'mesh', openedAt: 1 },
      { id: 'y', path: touch('ok.stl'), kind: 'other', openedAt: 1 },
    ];
    writeFileSync(path.join(folder, 'edited.json'), JSON.stringify(entries));
    expect(new RecentFiles(path.join(folder, 'edited.json')).list()).toEqual([]);
  });
});
