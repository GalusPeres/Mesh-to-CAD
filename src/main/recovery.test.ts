import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  MAX_SESSION_AGE_MS,
  candidateDirectory,
  findRecoveryCandidates,
  isSessionLocked,
} from './recovery';

const sessions = path.resolve('C:/data/Mesh-to-CAD/sessions');
const candidates = [
  { id: '1790000000000-4242', startedAt: 1790000000000, label: 'halterung' },
  { id: '..', startedAt: 0, label: 'crafted' },
];

describe('candidateDirectory', () => {
  it('resolves a known candidate inside the sessions directory', () => {
    expect(candidateDirectory(sessions, candidates, '1790000000000-4242')).toBe(
      path.join(sessions, '1790000000000-4242'),
    );
  });

  it('rejects ids that are not current candidates', () => {
    expect(candidateDirectory(sessions, candidates, 'other')).toBeNull();
  });

  it('never leaves the sessions directory', () => {
    expect(candidateDirectory(sessions, candidates, '..')).toBeNull();
  });
});

const NOW = 1_790_000_000_000;
let root: string;

/** A session directory as the kernel writes it; `scan` null gives an empty head revision. */
function session(name: string, options: { started: number; scan: string | null }): string {
  const directory = path.join(root, name);
  mkdirSync(path.join(directory, 'revisions'), { recursive: true });
  writeFileSync(path.join(directory, 'session.lock'), '');
  writeFileSync(
    path.join(directory, 'session.json'),
    JSON.stringify({ pid: 4242, started: options.started / 1000 }),
  );
  writeFileSync(path.join(directory, 'head.json'), JSON.stringify({ head: 3, next: 4 }));
  const scan = options.scan && { source: { fileName: options.scan, sha256: '', importUnit: 'mm' } };
  const document = { format: 'mesh-to-cad-document', version: 1, document: { scan } };
  writeFileSync(
    path.join(directory, 'revisions', '3.json'),
    JSON.stringify({ label: 'repair', meshChanging: true, document }),
  );
  return directory;
}

beforeEach(() => {
  root = mkdtempSync(path.join(tmpdir(), 'm2c-sessions-'));
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

describe('findRecoveryCandidates', () => {
  it('offers crashed sessions with a scan, newest first, labelled with the scan', () => {
    session('a', { started: NOW - 60_000, scan: 'halterung_scan.stl' });
    session('b', { started: NOW - 30_000, scan: 'flansch.ply' });
    const found = findRecoveryCandidates(root, path.join(root, 'current'), { now: NOW });
    expect(found).toEqual([
      { id: 'b', startedAt: NOW - 30_000, label: 'flansch.ply' },
      { id: 'a', startedAt: NOW - 60_000, label: 'halterung_scan.stl' },
    ]);
  });

  it('skips the current and locked sessions without touching them', () => {
    const current = session('current', { started: NOW, scan: 'a.stl' });
    const running = session('running', { started: NOW, scan: 'b.stl' });
    const found = findRecoveryCandidates(root, current, {
      now: NOW,
      isLocked: (directory) => directory === running,
    });
    expect(found).toEqual([]);
    expect(existsSync(current) && existsSync(running)).toBe(true);
  });

  it('deletes sessions older than seven days and sessions without a scan', () => {
    const old = session('old', { started: NOW - MAX_SESSION_AGE_MS - 1, scan: 'a.stl' });
    const empty = session('empty', { started: NOW, scan: null });
    const broken = path.join(root, 'broken');
    mkdirSync(broken);
    expect(findRecoveryCandidates(root, path.join(root, 'x'), { now: NOW })).toEqual([]);
    expect(existsSync(old) || existsSync(empty) || existsSync(broken)).toBe(false);
  });

  it('falls back to the directory name for the start time', () => {
    const directory = session(`${NOW - 5_000}-77`, { started: 0, scan: 'a.stl' });
    rmSync(path.join(directory, 'session.json'));
    const [found] = findRecoveryCandidates(root, path.join(root, 'x'), { now: NOW });
    expect(found?.startedAt).toBe(NOW - 5_000);
  });

  it('returns nothing when the sessions directory does not exist', () => {
    expect(findRecoveryCandidates(path.join(root, 'missing'), root)).toEqual([]);
  });
});

const python = path.resolve('.venv', 'Scripts', 'python.exe');
const lockScript = [
  'import sys, msvcrt',
  'handle = open(sys.argv[1], "a+b")',
  'msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)',
  'print("locked", flush=True)',
  'sys.stdin.read()',
].join('\n');

describe('isSessionLocked', () => {
  it.skipIf(process.platform !== 'win32' || !existsSync(python))(
    'sees the lock of a running kernel and its release',
    async () => {
      const directory = session('live', { started: NOW, scan: 'a.stl' });
      const holder = spawn(python, ['-c', lockScript, path.join(directory, 'session.lock')]);
      await new Promise<void>((resolve, reject) => {
        holder.stdout.on('data', () => resolve());
        holder.on('error', reject);
      });
      expect(isSessionLocked(directory)).toBe(true);
      holder.stdin.end();
      await new Promise((resolve) => holder.on('exit', resolve));
      expect(isSessionLocked(directory)).toBe(false);
    },
  );

  it('treats a session without a lock file as free', () => {
    expect(isSessionLocked(root)).toBe(false);
  });
});
