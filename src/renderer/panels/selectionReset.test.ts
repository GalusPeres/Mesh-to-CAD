import { describe, expect, it } from 'vitest';

import { keptSelection } from './selectionReset';

const snapshot = (scanKey: string | null, features: string[], cause = 'commit') =>
  ({
    cause,
    document: {
      scan: scanKey ? { key: scanKey } : null,
      features: features.map((id) => ({ id })),
      regions: { items: [] },
    },
    status: { bodies: [] },
  }) as never;

const plane = { kind: 'feature', id: 'f1' } as const;

describe('tree choice across documents', () => {
  it('keeps chosen objects while the document goes on', () => {
    expect(keptSelection([plane], snapshot('a', ['f1', 'f2']), snapshot('a', ['f1']))).toEqual([
      plane,
    ]);
  });

  it('drops objects that are gone', () => {
    expect(keptSelection([plane], snapshot('a', []), snapshot('a', ['f1']))).toEqual([]);
  });

  it('starts a new scan or a loaded project with nothing chosen, though ids repeat', () => {
    expect(keptSelection([plane], snapshot('b', ['f1']), snapshot('a', ['f1']))).toEqual([]);
    expect(keptSelection([plane], snapshot('a', ['f1'], 'restore'), snapshot('a', ['f1']))).toEqual(
      [],
    );
  });
});
