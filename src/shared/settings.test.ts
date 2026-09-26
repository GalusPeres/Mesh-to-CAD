import { describe, expect, it } from 'vitest';

import { DEFAULT_SETTINGS, applySettingsPatch, validateSettings } from './settings';

describe('settings', () => {
  it('fall back to defaults for missing or invalid values', () => {
    expect(validateSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(
      validateSettings({ language: 'fr', theme: 'pink', navigation: { invertWheel: 'yes' } }),
    ).toEqual(DEFAULT_SETTINGS);
  });

  it('merge patches into nested groups', () => {
    const patched = applySettingsPatch(DEFAULT_SETTINGS, {
      language: 'en',
      navigation: { invertWheel: true },
      tools: { 'select-brush': { radius: 24 } },
    });
    expect(patched.language).toBe('en');
    expect(patched.navigation.invertWheel).toBe(true);
    expect(patched.selection.clearAfterFit).toBe(true);
    expect(patched.tools['select-brush']).toEqual({ radius: 24 });
  });
});
