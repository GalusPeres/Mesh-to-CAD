import type { TFunction } from 'i18next';
import { Box } from 'lucide-react';
import { beforeAll, describe, expect, it } from 'vitest';

import type { RecentFile } from '@shared/bridge';
import { applySettingsPatch, DEFAULT_SETTINGS } from '@shared/settings';

import { recentRows } from '../app/empty-state/recentFiles';
import { findShortcutConflicts } from '../app/commands/keymap';
import { allCommands } from '../app/commands/registry';
import type { AppCommand } from '../app/commands/types';
import { commands as helpCommands } from '../help/help.commands';
import { activeHelpTopic, helpLanguage } from '../help/openHelp';
import { testTranslator } from '../panels/fixtures';
import { toolStore } from '../state/toolStore';
import { commands as settingsCommands } from './settings.commands';
import { hasStoredToolOptions, resetToolOptionsPatch } from './settingsModel';
import { shortcutSections } from './shortcutHelp';

let t: TFunction;
let tEnglish: TFunction;

beforeAll(async () => {
  t = await testTranslator('de');
  tEnglish = await testTranslator('en');
});

describe('settings dialog logic', () => {
  it('resets remembered tool options and keeps the other settings', () => {
    const settings = applySettingsPatch(DEFAULT_SETTINGS, {
      language: 'en',
      navigation: { invertWheel: true },
      tools: { 'select-brush': { size: 24 }, 'fit-primitive': { sections: { result: false } } },
    });
    expect(hasStoredToolOptions(settings)).toBe(true);
    const patch = resetToolOptionsPatch(settings);
    expect(patch).toEqual({ tools: { 'select-brush': {}, 'fit-primitive': {} } });
    const reset = applySettingsPatch(settings, patch ?? {});
    expect(hasStoredToolOptions(reset)).toBe(false);
    expect(resetToolOptionsPatch(reset)).toBeNull();
    expect(reset.language).toBe('en');
    expect(reset.navigation.invertWheel).toBe(true);
  });

  it('writes the typed preferences through settings patches', () => {
    const patched = applySettingsPatch(DEFAULT_SETTINGS, { selection: { clearAfterFit: false } });
    expect(patched.selection.clearAfterFit).toBe(false);
    expect(applySettingsPatch(patched, { theme: 'light' }).selection.clearAfterFit).toBe(false);
  });
});

describe('shortcut help', () => {
  const command = (id: string, extra: Partial<AppCommand> = {}): AppCommand => ({
    id,
    label: `common:commands.${id.split('.')[1] ?? id}`,
    run: () => undefined,
    ...extra,
  });

  it('lists commands with keys by section, in menu order, with keys in the UI language', () => {
    const sections = shortcutSections(
      [
        command('edit.redo', {
          shortcuts: [
            { key: 'y', ctrl: true },
            { key: 'z', ctrl: true, shift: true },
          ],
          placement: { menu: 'edit', group: 1, order: 2 },
        }),
        command('edit.undo', {
          shortcuts: [{ key: 'z', ctrl: true }],
          placement: { menu: 'edit', group: 1, order: 1 },
        }),
        command('app.quit', { placement: { menu: 'file', group: 9, order: 1 } }),
        command('tool.extrude', {
          label: 'tools:extrude.label',
          icon: Box,
          shortcuts: [{ key: 'E' }],
        }),
        command('strange.thing', {
          label: 'common:commands.settings',
          shortcuts: [{ key: 'Delete' }],
        }),
      ],
      t,
      'de',
    );
    expect(sections.map((section) => section.id)).toEqual([
      'edit',
      'tools',
      'toolPanel',
      'tree',
      'other',
    ]);
    expect(sections[0]).toEqual({
      id: 'edit',
      title: 'Bearbeiten',
      rows: [
        { id: 'edit.undo', label: 'Rückgängig', keys: ['Strg+Z'] },
        { id: 'edit.redo', label: 'Wiederholen', keys: ['Strg+Y', 'Strg+Umschalt+Z'] },
      ],
    });
    expect(sections[1]?.rows[0]).toMatchObject({ id: 'tool.extrude', keys: ['E'] });
    expect(sections.at(-1)?.rows[0]?.keys).toEqual(['Entf']);
    expect(sections.find((section) => section.id === 'toolPanel')?.rows).toEqual([
      { id: 'toolPanel.commit', label: 'OK', keys: ['Eingabe'] },
      { id: 'toolPanel.apply', label: 'Anwenden', keys: ['Umschalt+Eingabe'] },
      { id: 'toolPanel.cancel', label: 'Abbrechen', keys: ['Esc'] },
    ]);
    // Hide and show share H and are listed once.
    expect(
      sections.find((section) => section.id === 'tree')?.rows.map((row) => row.keys[0]),
    ).toEqual(['Eingabe', 'F2', 'H', 'Entf']);
  });

  it('covers every registered shortcut and translates it in both languages', () => {
    const registered = allCommands().filter((item) => item.shortcuts?.length);
    for (const [translate, language] of [
      [t, 'de'],
      [tEnglish, 'en'],
    ] as const) {
      const rows = shortcutSections(allCommands(), translate, language).flatMap((s) => s.rows);
      for (const item of registered) {
        const row = rows.find((candidate) => candidate.id === item.id);
        expect(row, item.id).toBeDefined();
        expect(row?.label, item.id).not.toBe(item.label);
      }
    }
    expect(shortcutSections(allCommands(), tEnglish, 'en')[0]?.title).toBe('File');
  });

  it('adds help, settings and shortcut commands without key conflicts', () => {
    const ids = allCommands().map((item) => item.id);
    for (const item of [...helpCommands, ...settingsCommands]) expect(ids).toContain(item.id);
    expect(findShortcutConflicts(allCommands())).toEqual([]);
    const f1 = helpCommands.find((item) => item.id === 'help.tool');
    expect(f1?.shortcuts).toEqual([{ key: 'F1' }]);
    expect(f1?.inTextFields).toBe(true);
    expect(helpCommands.find((item) => item.id === 'help.shortcuts')?.shortcuts).toEqual([
      { key: '/', ctrl: true },
    ]);
  });
});

describe('help', () => {
  it('opens the page of the open tool, then of the selection mode, else the index', () => {
    toolStore.setState({ activeToolId: null, selectionMode: null });
    expect(activeHelpTopic()).toBe('index');
    toolStore.setState({ selectionMode: 'select-brush' });
    expect(activeHelpTopic()).toBe('select-brush');
    toolStore.setState({ activeToolId: 'fit-primitive' });
    expect(activeHelpTopic()).toBe('fit-primitive');
    toolStore.setState({ activeToolId: null, selectionMode: null });
    expect(helpLanguage('en')).toBe('en');
    expect(helpLanguage('fr')).toBe('de');
  });
});

describe('recent files in the empty state', () => {
  it('shows the five most recently opened files, newest first', () => {
    const file = (id: string, openedAt: number): RecentFile => ({
      id,
      name: `${id}.stl`,
      folder: 'C:\\Scans',
      kind: 'mesh',
      openedAt,
    });
    const rows = recentRows([1, 7, 3, 9, 2, 8, 5].map((time) => file(`f${time}`, time)));
    expect(rows.map((row) => row.id)).toEqual(['f9', 'f8', 'f7', 'f5', 'f3']);
  });
});
