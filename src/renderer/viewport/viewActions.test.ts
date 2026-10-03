import { afterEach, describe, expect, it } from 'vitest';

import { setDisplayMode, setVisibility, viewStore } from '../state/viewStore';
import { cycleVisibility, nextVisibility, toggleXray } from './viewActions';

afterEach(() => {
  setVisibility('both');
  setDisplayMode('shaded');
});

describe('visibility cycling', () => {
  it('goes from scan and bodies to only the scan, only the bodies and back', () => {
    expect(nextVisibility('both')).toBe('scan');
    expect(nextVisibility('scan')).toBe('bodies');
    expect(nextVisibility('bodies')).toBe('both');
  });

  it('updates the view store on every press', () => {
    const seen: string[] = [];
    for (let press = 0; press < 3; press += 1) {
      cycleVisibility();
      seen.push(viewStore.getState().visibility);
    }
    expect(seen).toEqual(['scan', 'bodies', 'both']);
  });
});

describe('x-ray toggle', () => {
  it('returns to the display mode shown before', () => {
    setDisplayMode('regions');
    toggleXray();
    expect(viewStore.getState().displayMode).toBe('xray');
    toggleXray();
    expect(viewStore.getState().displayMode).toBe('regions');
  });
});
