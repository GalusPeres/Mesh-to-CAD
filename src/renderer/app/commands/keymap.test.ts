import { describe, expect, it } from 'vitest';

import { findShortcutConflicts, formatShortcut, matchesShortcut, resolveShortcut } from './keymap';
import type { AppCommand } from './types';

const key = (key: string, modifiers: { ctrl?: boolean; shift?: boolean; alt?: boolean } = {}) => ({
  key,
  ctrlKey: !!modifiers.ctrl,
  metaKey: false,
  shiftKey: !!modifiers.shift,
  altKey: !!modifiers.alt,
});

const command = (id: string, extra: Partial<AppCommand>): AppCommand => ({
  id,
  label: id,
  run: () => undefined,
  ...extra,
});

describe('keymap', () => {
  it('formats shortcuts per language', () => {
    expect(formatShortcut({ key: 'I', ctrl: true, shift: true }, 'de')).toBe('Strg+Umschalt+I');
    expect(formatShortcut({ key: 'I', ctrl: true, shift: true }, 'en')).toBe('Ctrl+Shift+I');
    expect(formatShortcut({ key: 'Delete' }, 'de')).toBe('Entf');
  });

  it('matches keys case-insensitively and checks modifiers', () => {
    expect(matchesShortcut(key('Z', { ctrl: true }), { key: 'z', ctrl: true })).toBe(true);
    expect(matchesShortcut(key('z', { ctrl: true, shift: true }), { key: 'z', ctrl: true })).toBe(
      false,
    );
    expect(matchesShortcut(key('[', { shift: true }), { key: '[' })).toBe(true);
  });

  it('never fires viewport shortcuts in text fields', () => {
    const fit = command('view.fitAll', { shortcuts: [{ key: 'f' }], scope: 'viewport' });
    const importScan = command('file.importScan', {
      shortcuts: [{ key: 'i', ctrl: true }],
      inTextFields: true,
    });
    const context = { inTextField: true, sketchMode: false };
    expect(resolveShortcut(key('f'), [fit], context)).toBeUndefined();
    expect(resolveShortcut(key('i', { ctrl: true }), [importScan], context)).toBe(importScan);
  });

  it('prefers the sketch scope in sketch mode', () => {
    const line = command('sketch.line', { shortcuts: [{ key: 'l' }], scope: 'sketch' });
    const lasso = command('tool.select-lasso', { shortcuts: [{ key: 'l' }], scope: 'viewport' });
    expect(resolveShortcut(key('l'), [lasso, line], { inTextField: false, sketchMode: true })).toBe(
      line,
    );
    expect(
      resolveShortcut(key('l'), [lasso, line], { inTextField: false, sketchMode: false }),
    ).toBe(lasso);
  });

  it('finds duplicate shortcuts within a scope', () => {
    const a = command('a', { shortcuts: [{ key: 'x' }], scope: 'viewport' });
    const b = command('b', { shortcuts: [{ key: 'X' }], scope: 'viewport' });
    const c = command('c', { shortcuts: [{ key: 'x' }], scope: 'sketch' });
    expect(findShortcutConflicts([a, b, c])).toEqual([['a', 'b']]);
  });
});
