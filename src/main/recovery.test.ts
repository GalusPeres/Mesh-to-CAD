import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { candidateDirectory } from './recovery';

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
