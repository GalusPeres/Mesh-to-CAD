import { describe, expect, it } from 'vitest';

import { productNames, safeFileName } from './exportFlow';

describe('export names', () => {
  const names = new Map([
    ['f5', 'Körper 1'],
    ['f9', 'Körper 2'],
  ]);
  const combine = (project: string, body: string) => `${project} ${body}`;

  it('names a single body after the project', () => {
    expect(productNames('Halterung', ['f5'], names, combine)).toEqual(['Halterung']);
  });

  it('adds the body name when several bodies are exported', () => {
    expect(productNames('Halterung', ['f5', 'f9'], names, combine)).toEqual([
      'Halterung Körper 1',
      'Halterung Körper 2',
    ]);
  });

  it('removes characters Windows does not allow in file names', () => {
    expect(safeFileName('Deckel: Rev. 2/3')).toBe('Deckel_ Rev. 2_3');
    expect(safeFileName('  ')).toBe('export');
    expect(safeFileName('Gehäuse')).toBe('Gehäuse');
  });
});
